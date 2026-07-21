"""Dockerize an agent + treatment and collect token telemetry from the container."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from skill_token_bench.agents.base import AgentRunRequest, AgentRunResponse
from skill_token_bench.agents.claude_code import parse_usage_blob
from skill_token_bench.metrics.pricing import estimate_cost
from skill_token_bench.models import TokenUsage, TreatmentKind


def build_agent_image(repo_root: Path, tag: str = "skill-token-bench/agent-base:latest") -> None:
    docker_dir = repo_root / "docker" / "agent-base"
    subprocess.run(
        ["docker", "build", "-t", tag, str(docker_dir)],
        check=True,
    )


def run_in_docker(request: AgentRunRequest) -> AgentRunResponse:
    if not shutil.which("docker"):
        return AgentRunResponse(
            output_text="",
            tokens=TokenUsage(),
            success=False,
            error="docker not found on PATH",
        )

    run_dir = Path(request.metadata["run_dir"])
    container_workspace = "/workspace"
    container_skills = "/skills"
    container_bin = "/stb/bin"

    mounts: list[str] = [
        "-v",
        f"{request.workspace.resolve()}:{container_workspace}",
    ]
    env_args: list[str] = [
        "-e",
        f"STB_MODEL={request.agent.model}",
        "-e",
        f"STB_AGENT={request.agent.kind.value}",
        "-e",
        f"STB_TREATMENT={request.treatment.name}",
        "-e",
        f"STB_TREATMENT_KIND={request.treatment.kind.value}",
    ]
    for key, value in {**request.agent.env, **request.treatment.env, **request.env}.items():
        # Don't pass host PATH literally into the container.
        if key == "PATH" and value.startswith("/"):
            continue
        env_args.extend(["-e", f"{key}={value}"])

    # Forward API keys when present on the host.
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CURSOR_API_KEY"):
        if os.environ.get(key):
            env_args.extend(["-e", key])

    path_prefix = ""
    if request.skill_mount and request.skill_mount.exists():
        mounts.extend(["-v", f"{request.skill_mount.resolve()}:{container_skills}:ro"])
        env_args.extend(["-e", f"STB_SKILL_DIR={container_skills}"])

    bin_dir = request.metadata.get("bin_dir")
    if bin_dir:
        bin_path = Path(bin_dir)
        if bin_path.exists():
            mounts.extend(["-v", f"{bin_path.resolve()}:{container_bin}:ro"])
            path_prefix = f"{container_bin}:"

    prompt_file = run_dir / "prompt.txt"
    prompt_file.write_text(_compose_prompt(request), encoding="utf-8")
    mounts.extend(["-v", f"{prompt_file.resolve()}:/stb/prompt.txt:ro"])

    image = request.agent.image
    cmd = [
        "docker",
        "run",
        "--rm",
        "-w",
        container_workspace,
        *mounts,
        *env_args,
        "-e",
        f"PATH={path_prefix}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        image,
        "python",
        "/stb/entrypoint.py",
    ]

    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=request.task.timeout_seconds + 30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return AgentRunResponse(
            output_text="",
            tokens=TokenUsage(),
            success=False,
            error="docker run timed out",
        )
    wall = time.perf_counter() - started

    raw_out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (run_dir / "docker.stdout").write_text(proc.stdout or "", encoding="utf-8")
    (run_dir / "docker.stderr").write_text(proc.stderr or "", encoding="utf-8")

    # Entrypoint prints a final JSON line with usage + result.
    payload = _extract_json_result(proc.stdout or "")
    if payload:
        tokens = TokenUsage.model_validate(payload.get("tokens") or {})
        output_text = str(payload.get("output_text") or "")
        success = bool(payload.get("success"))
        error = payload.get("error")
    else:
        tokens = parse_usage_blob(raw_out) or TokenUsage()
        output_text = proc.stdout or ""
        success = proc.returncode == 0
        error = None if success else (proc.stderr or f"exit {proc.returncode}")

    tokens.estimated_cost_usd = estimate_cost(request.agent.model, tokens)
    return AgentRunResponse(
        output_text=output_text,
        tokens=tokens,
        success=success,
        error=error,
        metadata={"wall_seconds": wall, "docker": True, "returncode": proc.returncode},
    )


def _compose_prompt(request: AgentRunRequest) -> str:
    prompt = request.task.prompt
    if request.treatment.kind == TreatmentKind.SKILL and request.skill_mount:
        skill_md = request.skill_mount / "SKILL.md"
        if not skill_md.exists():
            matches = list(request.skill_mount.rglob("SKILL.md"))
            skill_md = matches[0] if matches else skill_md
        if skill_md.exists():
            return (
                "Follow this skill strictly:\n\n"
                f"{skill_md.read_text(encoding='utf-8')}\n\n---\n\n"
                f"User task:\n{prompt}"
            )
    return prompt


def _extract_json_result(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "tokens" in data:
            return data
    return None

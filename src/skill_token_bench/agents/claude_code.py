"""Claude Code CLI adapter.

Runs `claude -p` (print mode) optionally inside Docker, then parses token usage
from JSON / stderr telemetry when available.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from skill_token_bench.agents.base import AgentAdapter, AgentRunRequest, AgentRunResponse
from skill_token_bench.metrics.pricing import estimate_cost
from skill_token_bench.models import TokenUsage, TreatmentKind


USAGE_RE = re.compile(
    r'"(?:input_tokens|prompt_tokens)"\s*:\s*(\d+).*?'
    r'"(?:output_tokens|completion_tokens)"\s*:\s*(\d+)',
    re.DOTALL,
)


def parse_usage_blob(text: str) -> TokenUsage | None:
    """Best-effort parse of Claude / Anthropic usage JSON fragments."""
    # Prefer full JSON objects.
    for candidate in _json_candidates(text):
        usage = _usage_from_obj(candidate)
        if usage:
            return usage
    match = USAGE_RE.search(text)
    if match:
        return TokenUsage(input_tokens=int(match.group(1)), output_tokens=int(match.group(2)))
    return None


def _json_candidates(text: str) -> list[Any]:
    out: list[Any] = []
    text = text.strip()
    if not text:
        return out
    try:
        out.append(json.loads(text))
        return out
    except json.JSONDecodeError:
        pass
    # NDJSON / embedded objects
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _usage_from_obj(obj: Any) -> TokenUsage | None:
    if not isinstance(obj, dict):
        return None
    usage = obj.get("usage") or obj.get("token_usage") or obj
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    return TokenUsage(
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        cache_read_tokens=int(usage.get("cache_read_input_tokens") or usage.get("cache_read_tokens") or 0),
        cache_write_tokens=int(
            usage.get("cache_creation_input_tokens") or usage.get("cache_write_tokens") or 0
        ),
        raw=usage,
    )


class ClaudeCodeAgent(AgentAdapter):
    kind = "claude-code"

    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        if request.metadata.get("use_docker"):
            from skill_token_bench.docker.runner import run_in_docker

            return run_in_docker(request)

        return self._run_local(request)

    def _run_local(self, request: AgentRunRequest) -> AgentRunResponse:
        if not shutil.which("claude"):
            return AgentRunResponse(
                output_text="",
                tokens=TokenUsage(),
                success=False,
                error="claude CLI not found on PATH; use agent.kind=mock or docker=true",
            )

        env = os.environ.copy()
        env.update(request.agent.env)
        env.update(request.treatment.env)
        env.update(request.env)

        prompt = request.task.prompt
        if request.treatment.kind == TreatmentKind.SKILL and request.skill_mount:
            skill_md = _find_skill_md(request.skill_mount)
            if skill_md:
                prompt = (
                    f"Follow this skill strictly:\n\n{skill_md.read_text(encoding='utf-8')}\n\n"
                    f"---\n\nUser task:\n{request.task.prompt}"
                )

        cmd = [
            "claude",
            "-p",
            prompt,
            "--model",
            request.agent.model,
            "--output-format",
            "json",
        ]
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(request.workspace),
                env=env,
                capture_output=True,
                text=True,
                timeout=request.task.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return AgentRunResponse(
                output_text="",
                tokens=TokenUsage(),
                success=False,
                error=f"timed out after {request.task.timeout_seconds}s",
            )

        wall = time.perf_counter() - started
        blob = (proc.stdout or "") + "\n" + (proc.stderr or "")
        tokens = parse_usage_blob(blob) or TokenUsage()
        tokens.estimated_cost_usd = estimate_cost(request.agent.model, tokens)

        output_text = proc.stdout or ""
        try:
            parsed = json.loads(proc.stdout or "")
            if isinstance(parsed, dict) and "result" in parsed:
                output_text = str(parsed["result"])
        except json.JSONDecodeError:
            pass

        success = proc.returncode == 0
        if request.task.success_regex:
            success = bool(re.search(request.task.success_regex, output_text, re.I))

        return AgentRunResponse(
            output_text=output_text,
            tokens=tokens,
            success=success,
            error=None if success else (proc.stderr or f"exit {proc.returncode}"),
            metadata={"wall_seconds": wall, "returncode": proc.returncode},
        )


def _find_skill_md(root: Path) -> Path | None:
    direct = root / "SKILL.md"
    if direct.exists():
        return direct
    matches = list(root.rglob("SKILL.md"))
    return matches[0] if matches else None

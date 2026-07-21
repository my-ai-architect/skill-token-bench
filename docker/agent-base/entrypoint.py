#!/usr/bin/env python3
"""Container entrypoint: run prompt via Claude CLI or deterministic mock, emit JSON telemetry."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def mock_run(prompt: str, treatment_kind: str, model: str) -> dict:
    verbose = (
        "Great question! Let me think about this carefully.\n\n"
        f"{prompt}\n\n"
        "There are several approaches worth considering. First examine context, "
        "then edge cases, then tests. This pattern shows up often. Hope this helps!"
    )
    concise = (
        "Do this next:\n"
        f"1. Address: {prompt[:160]}\n"
        "2. Verify.\n"
        "Next: paste the first failing line if needed."
    )
    answer = concise if treatment_kind == "skill" else verbose
    tool_payload = 0
    if "```" in prompt or "code" in prompt.lower() or "refactor" in prompt.lower():
        tool_payload = 2400
        if treatment_kind == "cli_intercept":
            tool_payload = int(tool_payload * 0.25)
    skill_overhead = 90 if treatment_kind == "skill" else 0
    cache_read = 600 if treatment_kind == "memory" else 0
    tokens = {
        "input_tokens": approx_tokens(prompt) + skill_overhead + tool_payload,
        "output_tokens": approx_tokens(answer),
        "cache_read_tokens": cache_read,
        "cache_write_tokens": 0,
        "total_tokens": 0,
    }
    tokens["total_tokens"] = (
        tokens["input_tokens"]
        + tokens["output_tokens"]
        + tokens["cache_read_tokens"]
        + tokens["cache_write_tokens"]
    )
    return {
        "output_text": answer,
        "tokens": tokens,
        "success": True,
        "error": None,
        "metadata": {"mode": "mock", "model": model},
    }


def claude_run(prompt: str, model: str, timeout: int) -> dict:
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "json"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return mock_run(prompt, os.environ.get("STB_TREATMENT_KIND", "none"), model)
    except subprocess.TimeoutExpired:
        return {
            "output_text": "",
            "tokens": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "total_tokens": 0,
            },
            "success": False,
            "error": "claude timed out",
            "metadata": {"mode": "claude-code"},
        }

    output = proc.stdout or ""
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 0,
    }
    try:
        parsed = json.loads(output)
        if isinstance(parsed, dict):
            output = str(parsed.get("result") or output)
            u = parsed.get("usage") or {}
            usage["input_tokens"] = int(u.get("input_tokens") or 0)
            usage["output_tokens"] = int(u.get("output_tokens") or 0)
            usage["cache_read_tokens"] = int(u.get("cache_read_input_tokens") or 0)
            usage["cache_write_tokens"] = int(u.get("cache_creation_input_tokens") or 0)
    except json.JSONDecodeError:
        pass
    usage["total_tokens"] = (
        usage["input_tokens"]
        + usage["output_tokens"]
        + usage["cache_read_tokens"]
        + usage["cache_write_tokens"]
    )
    return {
        "output_text": output,
        "tokens": usage,
        "success": proc.returncode == 0,
        "error": None if proc.returncode == 0 else (proc.stderr or f"exit {proc.returncode}"),
        "metadata": {"mode": "claude-code", "returncode": proc.returncode},
    }


def main() -> int:
    prompt_path = Path("/stb/prompt.txt")
    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read()

    agent = os.environ.get("STB_AGENT", "mock")
    model = os.environ.get("STB_MODEL", "mock-haiku")
    treatment_kind = os.environ.get("STB_TREATMENT_KIND", "none")
    timeout = int(os.environ.get("STB_TIMEOUT", "300"))

    # Prepend skill text when mounted and not already composed by host.
    skill_dir = os.environ.get("STB_SKILL_DIR")
    if skill_dir and "Follow this skill strictly" not in prompt:
        skill_md = Path(skill_dir) / "SKILL.md"
        if not skill_md.exists():
            matches = list(Path(skill_dir).rglob("SKILL.md"))
            skill_md = matches[0] if matches else skill_md
        if skill_md.exists():
            prompt = (
                "Follow this skill strictly:\n\n"
                f"{skill_md.read_text(encoding='utf-8')}\n\n---\n\n"
                f"User task:\n{prompt}"
            )

    if agent == "claude-code" and os.environ.get("ANTHROPIC_API_KEY"):
        result = claude_run(prompt, model, timeout)
    else:
        result = mock_run(prompt, treatment_kind, model)

    # Optional success regex from env
    pattern = os.environ.get("STB_SUCCESS_REGEX")
    if pattern:
        result["success"] = bool(re.search(pattern, result["output_text"], re.I))

    print(json.dumps(result), flush=True)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())

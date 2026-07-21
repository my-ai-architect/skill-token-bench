"""Deterministic mock agent for offline tests and dry-runs.

Simulates token impact of treatments:
- skill (i-have-adhd): shorter, denser answers → fewer output tokens
- cli_intercept (rtk): smaller tool payloads → fewer input tokens on coding tasks
- memory (claude-mem): warmup adds cache writes; later turns read cache + shorter prompts
"""

from __future__ import annotations

import hashlib
import re
import time

from skill_token_bench.agents.base import AgentAdapter, AgentRunRequest, AgentRunResponse
from skill_token_bench.metrics.pricing import estimate_cost
from skill_token_bench.models import TokenUsage, TreatmentKind


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockAgent(AgentAdapter):
    kind = "mock"

    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        started = time.perf_counter()
        task = request.task
        treatment = request.treatment
        prompt = task.prompt

        verbose_answer = (
            "Great question! Let me think about this carefully. "
            f"Regarding your request ({task.id}): {prompt}\n\n"
            "There are several approaches worth considering. First, you might want to "
            "examine the surrounding context and related modules. Second, consider edge "
            "cases and how other callers might behave. Third, it can help to sketch the "
            "data flow before changing anything. After that, you'd probably want to run "
            "the relevant tests and maybe look at dependency versions overall. "
            "By the way, this pattern shows up in a lot of codebases. "
            "Hope this helps! Let me know if you want to dig deeper or explore alternatives."
        )
        concise_answer = (
            f"Do this for `{task.id}`:\n"
            f"1. Apply the change implied by: {prompt[:120]}\n"
            "2. Verify with the suite check.\n"
            "Next: paste the first failing line if anything breaks."
        )

        if treatment.kind == TreatmentKind.SKILL:
            answer = concise_answer
            skill_overhead = 90  # compact SKILL.md injected into context
        else:
            answer = verbose_answer
            skill_overhead = 0

        # Coding tasks simulate tool-loop token bloat.
        tool_payload = 0
        if task.kind.value == "coding":
            tool_payload = 2400
            if treatment.kind == TreatmentKind.CLI_INTERCEPT:
                tool_payload = int(tool_payload * 0.25)  # rtk-style compression
            answer += "\n\n```diff\n- old\n+ new\n```\n"

        cache_read = 0
        cache_write = 0
        if treatment.kind == TreatmentKind.MEMORY:
            if request.metadata.get("warmup"):
                cache_write = 900
            else:
                cache_read = 600
                # Memory recall shortens re-stated context
                prompt = prompt[: max(40, len(prompt) // 2)]

        input_tokens = _approx_tokens(prompt) + skill_overhead + tool_payload
        output_tokens = _approx_tokens(answer)

        # Tiny deterministic jitter so repeats aren't bitwise identical.
        digest = hashlib.sha256(
            f"{task.id}:{treatment.name}:{request.metadata.get('repeat', 0)}".encode()
        ).hexdigest()
        jitter = int(digest[:2], 16) % 7

        tokens = TokenUsage(
            input_tokens=input_tokens + jitter,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
        tokens.estimated_cost_usd = estimate_cost(request.agent.model, tokens)

        success = True
        if task.success_regex:
            success = re.search(task.success_regex, answer, re.IGNORECASE) is not None

        # Simulate wall time proportional to tokens (not real latency).
        _ = time.perf_counter() - started
        wall_pad = 0.01 + (tokens.total_tokens / 100_000)

        return AgentRunResponse(
            output_text=answer,
            tokens=tokens,
            success=success,
            metadata={
                "mock": True,
                "treatment_kind": treatment.kind.value,
                "simulated_wall": wall_pad,
            },
        )

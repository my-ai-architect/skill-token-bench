from __future__ import annotations

from skill_token_bench.agents.base import AgentAdapter
from skill_token_bench.agents.claude_code import ClaudeCodeAgent
from skill_token_bench.agents.mock import MockAgent
from skill_token_bench.models import AgentKind


def get_agent(kind: AgentKind | str) -> AgentAdapter:
    key = kind.value if isinstance(kind, AgentKind) else kind
    if key == AgentKind.MOCK.value:
        return MockAgent()
    if key == AgentKind.CLAUDE_CODE.value:
        return ClaudeCodeAgent()
    if key in {AgentKind.CODEX.value, AgentKind.CURSOR.value}:
        raise NotImplementedError(
            f"Agent '{key}' adapter is stubbed — use mock or claude-code for now"
        )
    raise KeyError(f"Unknown agent kind: {key}")

"""Agent adapter SPI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skill_token_bench.models import AgentSpec, TaskSpec, TokenUsage, TreatmentSpec


@dataclass
class AgentRunRequest:
    task: TaskSpec
    agent: AgentSpec
    treatment: TreatmentSpec
    workspace: Path
    skill_mount: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunResponse:
    output_text: str
    tokens: TokenUsage
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentAdapter(ABC):
    kind: str

    @abstractmethod
    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        """Execute one task against the agent (local or via Docker helper)."""

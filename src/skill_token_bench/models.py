"""Shared pydantic models for experiments, runs, and metrics."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class TreatmentKind(str, Enum):
    NONE = "none"
    SKILL = "skill"
    CLI_INTERCEPT = "cli_intercept"
    MEMORY = "memory"
    CUSTOM = "custom"


class TaskKind(str, Enum):
    PROMPT = "prompt"
    CODING = "coding"
    MULTI_TURN = "multi_turn"


class AgentKind(str, Enum):
    MOCK = "mock"
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"
    CURSOR = "cursor"


class TokenUsage(BaseModel):
    """Durable token accounting for a single agent invocation."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.total_tokens:
            self.total_tokens = (
                self.input_tokens
                + self.output_tokens
                + self.cache_read_tokens
                + self.cache_write_tokens
            )


class TaskSpec(BaseModel):
    id: str
    kind: TaskKind = TaskKind.PROMPT
    prompt: str
    description: str = ""
    workspace_fixture: str | None = None
    success_regex: str | None = None
    max_turns: int = 1
    timeout_seconds: int = 300
    tags: list[str] = Field(default_factory=list)


class SuiteSpec(BaseModel):
    name: str
    description: str = ""
    tasks: list[TaskSpec]


class SourceSpec(BaseModel):
    git: str | None = None
    ref: str = "main"
    path: str | None = None
    local: str | None = None


class TreatmentSpec(BaseModel):
    name: str
    kind: TreatmentKind
    description: str = ""
    source: SourceSpec | None = None
    # Skill: relative path of SKILL.md inside source
    skill_path: str | None = None
    # CLI intercept: binary install + wrap list
    binary: str | None = None
    wrap_commands: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    # Memory: optional warmup task ids before measurement
    warmup_task_ids: list[str] = Field(default_factory=list)
    install_commands: list[str] = Field(default_factory=list)
    mount_path: str | None = None


class AgentSpec(BaseModel):
    kind: AgentKind = AgentKind.MOCK
    model: str = "mock-haiku"
    image: str = "skill-token-bench/agent-base:latest"
    env: dict[str, str] = Field(default_factory=dict)
    workdir: str = "/workspace"


class ExperimentSpec(BaseModel):
    name: str
    description: str = ""
    agent: AgentSpec
    suite: str
    baseline: str = "none"
    treatment: str
    repeats: int = 1
    seed: int = 42
    docker: bool = True
    output_dir: str = "results"


class TaskResult(BaseModel):
    task_id: str
    arm: Literal["baseline", "treatment"]
    repeat: int
    success: bool
    tokens: TokenUsage
    wall_seconds: float
    output_text: str = ""
    output_chars: int = 0
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArmSummary(BaseModel):
    arm: Literal["baseline", "treatment"]
    treatment_name: str
    runs: int
    success_rate: float
    mean_total_tokens: float
    mean_input_tokens: float
    mean_output_tokens: float
    mean_wall_seconds: float
    mean_output_chars: float
    mean_cost_usd: float | None = None


class DeltaSummary(BaseModel):
    """Treatment minus baseline. Negative token delta = savings."""

    total_tokens_delta: float
    total_tokens_pct: float | None = None
    input_tokens_delta: float
    output_tokens_delta: float
    wall_seconds_delta: float
    output_chars_delta: float
    success_rate_delta: float
    cost_usd_delta: float | None = None


class BenchmarkReport(BaseModel):
    experiment: str
    agent_kind: str
    model: str
    suite: str
    baseline: str
    treatment: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task_results: list[TaskResult]
    baseline_summary: ArmSummary
    treatment_summary: ArmSummary
    delta: DeltaSummary
    artifacts_dir: str | None = None

    def to_markdown(self) -> str:
        d = self.delta
        pct = f"{d.total_tokens_pct:+.1f}%" if d.total_tokens_pct is not None else "n/a"
        return "\n".join(
            [
                f"# Token efficiency: {self.experiment}",
                "",
                f"- Agent: `{self.agent_kind}` / `{self.model}`",
                f"- Suite: `{self.suite}`",
                f"- Baseline: `{self.baseline}` → Treatment: `{self.treatment}`",
                f"- Created: {self.created_at.isoformat()}",
                "",
                "## Summary",
                "",
                "| Arm | Success | Mean tokens | Mean in | Mean out | Mean wall (s) | Mean chars |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
                _arm_row(self.baseline_summary),
                _arm_row(self.treatment_summary),
                "",
                "## Delta (treatment − baseline)",
                "",
                f"- Total tokens: **{d.total_tokens_delta:+.1f}** ({pct})",
                f"- Input tokens: {d.input_tokens_delta:+.1f}",
                f"- Output tokens: {d.output_tokens_delta:+.1f}",
                f"- Wall seconds: {d.wall_seconds_delta:+.2f}",
                f"- Output chars: {d.output_chars_delta:+.1f}",
                f"- Success rate: {d.success_rate_delta:+.1%}",
                "",
                "_Negative token delta means the treatment used fewer tokens._",
            ]
        )


def _arm_row(s: ArmSummary) -> str:
    return (
        f"| {s.arm} ({s.treatment_name}) | {s.success_rate:.0%} | "
        f"{s.mean_total_tokens:.0f} | {s.mean_input_tokens:.0f} | "
        f"{s.mean_output_tokens:.0f} | {s.mean_wall_seconds:.2f} | "
        f"{s.mean_output_chars:.0f} |"
    )


class ResolvedPaths(BaseModel):
    root: Path
    suite_dir: Path
    baseline_dir: Path
    treatment_dir: Path
    output_dir: Path

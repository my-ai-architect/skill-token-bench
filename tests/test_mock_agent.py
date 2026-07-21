from pathlib import Path

from skill_token_bench.agents.base import AgentRunRequest
from skill_token_bench.agents.mock import MockAgent
from skill_token_bench.models import AgentSpec, TaskKind, TaskSpec, TreatmentKind, TreatmentSpec


def _req(treatment: TreatmentSpec, kind: TaskKind = TaskKind.PROMPT) -> AgentRunRequest:
    return AgentRunRequest(
        task=TaskSpec(id="t1", kind=kind, prompt="Explain git rebase briefly."),
        agent=AgentSpec(kind="mock", model="mock-haiku"),
        treatment=treatment,
        workspace=Path("."),
        metadata={"repeat": 0},
    )


def test_skill_reduces_output_tokens():
    agent = MockAgent()
    baseline = agent.run(
        _req(TreatmentSpec(name="none", kind=TreatmentKind.NONE))
    )
    treated = agent.run(
        _req(TreatmentSpec(name="i-have-adhd", kind=TreatmentKind.SKILL))
    )
    assert treated.tokens.output_tokens < baseline.tokens.output_tokens


def test_cli_intercept_reduces_coding_input_tokens():
    agent = MockAgent()
    baseline = agent.run(
        _req(TreatmentSpec(name="none", kind=TreatmentKind.NONE), kind=TaskKind.CODING)
    )
    treated = agent.run(
        _req(TreatmentSpec(name="rtk", kind=TreatmentKind.CLI_INTERCEPT), kind=TaskKind.CODING)
    )
    assert treated.tokens.input_tokens < baseline.tokens.input_tokens

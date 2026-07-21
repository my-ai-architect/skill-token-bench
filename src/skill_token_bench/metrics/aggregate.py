"""Aggregate per-task results into arm summaries and deltas."""

from __future__ import annotations

from statistics import mean

from skill_token_bench.models import ArmSummary, DeltaSummary, TaskResult


def summarize_arm(
    results: list[TaskResult],
    arm: str,
    treatment_name: str,
) -> ArmSummary:
    subset = [r for r in results if r.arm == arm]
    if not subset:
        return ArmSummary(
            arm=arm,  # type: ignore[arg-type]
            treatment_name=treatment_name,
            runs=0,
            success_rate=0.0,
            mean_total_tokens=0.0,
            mean_input_tokens=0.0,
            mean_output_tokens=0.0,
            mean_wall_seconds=0.0,
            mean_output_chars=0.0,
            mean_cost_usd=None,
        )
    costs = [r.tokens.estimated_cost_usd for r in subset if r.tokens.estimated_cost_usd is not None]
    return ArmSummary(
        arm=arm,  # type: ignore[arg-type]
        treatment_name=treatment_name,
        runs=len(subset),
        success_rate=mean(1.0 if r.success else 0.0 for r in subset),
        mean_total_tokens=mean(r.tokens.total_tokens for r in subset),
        mean_input_tokens=mean(r.tokens.input_tokens for r in subset),
        mean_output_tokens=mean(r.tokens.output_tokens for r in subset),
        mean_wall_seconds=mean(r.wall_seconds for r in subset),
        mean_output_chars=mean(r.output_chars for r in subset),
        mean_cost_usd=mean(costs) if costs else None,
    )


def summarize_delta(baseline: ArmSummary, treatment: ArmSummary) -> DeltaSummary:
    b = baseline.mean_total_tokens
    delta = treatment.mean_total_tokens - baseline.mean_total_tokens
    pct = (delta / b * 100.0) if b else None
    cost_delta = None
    if baseline.mean_cost_usd is not None and treatment.mean_cost_usd is not None:
        cost_delta = treatment.mean_cost_usd - baseline.mean_cost_usd
    return DeltaSummary(
        total_tokens_delta=delta,
        total_tokens_pct=pct,
        input_tokens_delta=treatment.mean_input_tokens - baseline.mean_input_tokens,
        output_tokens_delta=treatment.mean_output_tokens - baseline.mean_output_tokens,
        wall_seconds_delta=treatment.mean_wall_seconds - baseline.mean_wall_seconds,
        output_chars_delta=treatment.mean_output_chars - baseline.mean_output_chars,
        success_rate_delta=treatment.success_rate - baseline.success_rate,
        cost_usd_delta=cost_delta,
    )

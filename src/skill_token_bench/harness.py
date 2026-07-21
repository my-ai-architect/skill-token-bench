"""Before/after experiment runner."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from skill_token_bench.agents import get_agent
from skill_token_bench.agents.base import AgentRunRequest
from skill_token_bench.config import (
    load_experiment,
    load_suite,
    load_treatment,
    resolve_experiment_paths,
)
from skill_token_bench.metrics import estimate_cost, summarize_arm, summarize_delta
from skill_token_bench.models import (
    BenchmarkReport,
    ExperimentSpec,
    TaskResult,
    TreatmentKind,
)
from skill_token_bench.treatments import prepare_treatment

console = Console()


def run_experiment(
    experiment_path: Path,
    *,
    root: Path | None = None,
    fetch_remote: bool = False,
    use_docker: bool | None = None,
) -> BenchmarkReport:
    experiment = load_experiment(experiment_path)
    paths = resolve_experiment_paths(experiment, root)
    suite = load_suite(paths.suite_dir)
    baseline_spec = load_treatment(paths.baseline_dir)
    treatment_spec = load_treatment(paths.treatment_dir)

    docker = experiment.docker if use_docker is None else use_docker
    agent = get_agent(experiment.agent.kind)

    console.print(
        f"[bold]Running[/bold] {experiment.name} "
        f"({experiment.agent.kind.value}/{experiment.agent.model}) "
        f"suite={suite.name} baseline={baseline_spec.name} treatment={treatment_spec.name}"
    )

    results: list[TaskResult] = []
    for arm_name, t_spec, t_dir in (
        ("baseline", baseline_spec, paths.baseline_dir),
        ("treatment", treatment_spec, paths.treatment_dir),
    ):
        for repeat in range(experiment.repeats):
            staging = paths.output_dir / "staging" / arm_name / f"r{repeat}"
            if staging.exists():
                shutil.rmtree(staging)
            prepared = prepare_treatment(
                t_spec, t_dir, staging, fetch_remote=fetch_remote
            )

            for task in suite.tasks:
                # Memory treatments may declare warmup tasks.
                is_warmup = (
                    t_spec.kind == TreatmentKind.MEMORY
                    and task.id in t_spec.warmup_task_ids
                )
                run_dir = paths.output_dir / "runs" / arm_name / f"r{repeat}" / task.id
                run_dir.mkdir(parents=True, exist_ok=True)

                workspace = run_dir / "workspace"
                workspace.mkdir(parents=True, exist_ok=True)
                _stage_fixture(paths.suite_dir, task.workspace_fixture, workspace)

                request = AgentRunRequest(
                    task=task,
                    agent=experiment.agent,
                    treatment=t_spec,
                    workspace=workspace,
                    skill_mount=prepared.skill_dir,
                    env=prepared.env,
                    metadata={
                        "repeat": repeat,
                        "arm": arm_name,
                        "run_dir": str(run_dir),
                        "bin_dir": str(prepared.bin_dir) if prepared.bin_dir else None,
                        "use_docker": docker and experiment.agent.kind.value != "mock",
                        "warmup": is_warmup,
                    },
                )

                started = time.perf_counter()
                response = agent.run(request)
                wall = response.metadata.get("wall_seconds") or (
                    time.perf_counter() - started
                )
                if response.tokens.estimated_cost_usd is None:
                    response.tokens.estimated_cost_usd = estimate_cost(
                        experiment.agent.model, response.tokens
                    )

                # Warmup runs are recorded but tagged; still useful for memory cost.
                result = TaskResult(
                    task_id=task.id,
                    arm=arm_name,  # type: ignore[arg-type]
                    repeat=repeat,
                    success=response.success,
                    tokens=response.tokens,
                    wall_seconds=float(wall),
                    output_text=response.output_text,
                    output_chars=len(response.output_text),
                    error=response.error,
                    metadata={
                        **response.metadata,
                        "warmup": is_warmup,
                        "treatment_notes": prepared.notes,
                    },
                )
                results.append(result)
                _write_json(run_dir / "result.json", result.model_dump(mode="json"))
                (run_dir / "output.txt").write_text(response.output_text, encoding="utf-8")

                status = "ok" if response.success else "fail"
                console.print(
                    f"  [{arm_name} r{repeat}] {task.id}: {status} "
                    f"tokens={response.tokens.total_tokens} wall={float(wall):.2f}s"
                )

    # Summaries exclude pure warmup-only rows from success-sensitive means? Keep all
    # rows — warmup cost is part of the memory treatment's token impact.
    baseline_summary = summarize_arm(results, "baseline", baseline_spec.name)
    treatment_summary = summarize_arm(results, "treatment", treatment_spec.name)
    delta = summarize_delta(baseline_summary, treatment_summary)

    report = BenchmarkReport(
        experiment=experiment.name,
        agent_kind=experiment.agent.kind.value,
        model=experiment.agent.model,
        suite=suite.name,
        baseline=baseline_spec.name,
        treatment=treatment_spec.name,
        task_results=results,
        baseline_summary=baseline_summary,
        treatment_summary=treatment_summary,
        delta=delta,
        artifacts_dir=str(paths.output_dir),
    )
    _write_json(paths.output_dir / "report.json", report.model_dump(mode="json"))
    (paths.output_dir / "report.md").write_text(report.to_markdown(), encoding="utf-8")
    _print_summary(report)
    return report


def run_experiment_by_name(name: str, **kwargs) -> BenchmarkReport:
    root = kwargs.pop("root", None)
    from skill_token_bench.config import find_repo_root

    root = find_repo_root(root)
    path = root / "benchmarks" / "experiments" / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(path)
    return run_experiment(path, root=root, **kwargs)


def _stage_fixture(suite_dir: Path, fixture: str | None, workspace: Path) -> None:
    if not fixture:
        (workspace / "README.md").write_text("# workspace\n", encoding="utf-8")
        return
    src = (suite_dir / fixture).resolve()
    if not src.exists():
        raise FileNotFoundError(f"workspace fixture not found: {src}")
    if src.is_dir():
        shutil.copytree(src, workspace, dirs_exist_ok=True)
    else:
        shutil.copy2(src, workspace / src.name)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def _print_summary(report: BenchmarkReport) -> None:
    table = Table(title=f"Token impact: {report.treatment} vs {report.baseline}")
    table.add_column("Metric")
    table.add_column("Baseline", justify="right")
    table.add_column("Treatment", justify="right")
    table.add_column("Delta", justify="right")

    b, t, d = report.baseline_summary, report.treatment_summary, report.delta
    table.add_row("Mean total tokens", f"{b.mean_total_tokens:.0f}", f"{t.mean_total_tokens:.0f}", f"{d.total_tokens_delta:+.0f}")
    table.add_row("Mean input tokens", f"{b.mean_input_tokens:.0f}", f"{t.mean_input_tokens:.0f}", f"{d.input_tokens_delta:+.0f}")
    table.add_row("Mean output tokens", f"{b.mean_output_tokens:.0f}", f"{t.mean_output_tokens:.0f}", f"{d.output_tokens_delta:+.0f}")
    table.add_row("Success rate", f"{b.success_rate:.0%}", f"{t.success_rate:.0%}", f"{d.success_rate_delta:+.0%}")
    pct = f"{d.total_tokens_pct:+.1f}%" if d.total_tokens_pct is not None else "n/a"
    console.print(table)
    console.print(f"[bold]Token delta:[/bold] {d.total_tokens_delta:+.0f} ({pct})")
    console.print(f"Artifacts: {report.artifacts_dir}")


def load_and_validate(experiment_path: Path) -> ExperimentSpec:
    return load_experiment(experiment_path)

"""CLI: stb run | list | report | docker-build."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from skill_token_bench import __version__
from skill_token_bench.config import find_repo_root, load_experiment, load_suite, load_treatment
from skill_token_bench.harness import run_experiment
from skill_token_bench.models import BenchmarkReport

app = typer.Typer(
    name="stb",
    help="Skill Token Bench — measure token impact of skills, CLI intercepts, and memory tools.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def main() -> None:
    """Token-efficiency benchmarks for agent skills and tools."""


@app.command("version")
def version() -> None:
    console.print(__version__)


@app.command("list")
def list_assets(
    root: Optional[Path] = typer.Option(None, help="Repo root (auto-detected)"),
) -> None:
    """List suites, treatments, and experiments."""
    root = find_repo_root(root)
    table = Table(title="Benchmarks")
    table.add_column("Kind")
    table.add_column("Name")
    table.add_column("Path")

    for kind in ("suites", "treatments", "experiments"):
        base = root / "benchmarks" / kind
        if not base.exists():
            continue
        if kind == "experiments":
            for path in sorted(base.glob("*.yaml")):
                table.add_row(kind, path.stem, str(path.relative_to(root)))
        else:
            for path in sorted(p for p in base.iterdir() if p.is_dir()):
                table.add_row(kind, path.name, str(path.relative_to(root)))
    console.print(table)


@app.command("run")
def run(
    experiment: Path = typer.Argument(..., help="Experiment YAML path or name under benchmarks/experiments/"),
    root: Optional[Path] = typer.Option(None, help="Repo root"),
    fetch_remote: bool = typer.Option(
        False,
        "--fetch-remote/--no-fetch-remote",
        help="Clone treatment sources from git when no local fixture exists",
    ),
    docker: Optional[bool] = typer.Option(
        None,
        "--docker/--local",
        help="Force dockerized or local agent execution (default: experiment.docker)",
    ),
) -> None:
    """Run a before/after token-efficiency experiment."""
    root = find_repo_root(root)
    path = experiment
    if not path.exists():
        candidate = root / "benchmarks" / "experiments" / f"{experiment}.yaml"
        if candidate.exists():
            path = candidate
        else:
            raise typer.BadParameter(f"Experiment not found: {experiment}")

    report = run_experiment(path, root=root, fetch_remote=fetch_remote, use_docker=docker)
    console.print(f"[green]Wrote[/green] {Path(report.artifacts_dir or '.') / 'report.md'}")


@app.command("report")
def report_cmd(
    results_dir: Path = typer.Argument(..., help="Directory containing report.json"),
) -> None:
    """Re-print a saved report."""
    path = results_dir / "report.json" if results_dir.is_dir() else results_dir
    data = path.read_text(encoding="utf-8")
    report = BenchmarkReport.model_validate_json(data)
    console.print(report.to_markdown())


@app.command("docker-build")
def docker_build(
    root: Optional[Path] = typer.Option(None),
    tag: str = typer.Option("skill-token-bench/agent-base:latest", "--tag"),
) -> None:
    """Build the agent base image used for dockerized runs."""
    from skill_token_bench.docker import build_agent_image

    root = find_repo_root(root)
    build_agent_image(root, tag=tag)
    console.print(f"[green]Built[/green] {tag}")


@app.command("validate")
def validate(
    experiment: Path = typer.Argument(...),
    root: Optional[Path] = typer.Option(None),
) -> None:
    """Validate experiment + linked suite/treatments parse cleanly."""
    root = find_repo_root(root)
    path = experiment if experiment.exists() else root / "benchmarks" / "experiments" / f"{experiment}.yaml"
    exp = load_experiment(path)
    from skill_token_bench.config import resolve_experiment_paths

    paths = resolve_experiment_paths(exp, root)
    suite = load_suite(paths.suite_dir)
    baseline = load_treatment(paths.baseline_dir)
    treatment = load_treatment(paths.treatment_dir)
    console.print(
        f"[green]OK[/green] {exp.name}: suite={suite.name} "
        f"({len(suite.tasks)} tasks), baseline={baseline.name}, treatment={treatment.name}"
    )


if __name__ == "__main__":
    app()

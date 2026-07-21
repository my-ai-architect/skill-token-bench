"""Load YAML experiment / suite / treatment specs."""

from __future__ import annotations

from pathlib import Path

import yaml

from skill_token_bench.models import (
    ExperimentSpec,
    ResolvedPaths,
    SuiteSpec,
    TreatmentSpec,
)


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def find_repo_root(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "pyproject.toml").exists() and (
            candidate / "benchmarks"
        ).exists():
            return candidate
    return cur


def resolve_named_dir(root: Path, category: str, name: str) -> Path:
    """Resolve `suites/foo` or bare `foo` under benchmarks/<category>/."""
    name = name.rstrip("/")
    direct = root / name
    if direct.is_dir() and any(direct.glob("*.yaml")):
        return direct
    under = root / "benchmarks" / category / name
    if under.is_dir():
        return under
    raise FileNotFoundError(
        f"Could not find {category} '{name}' under {root / 'benchmarks' / category}"
    )


def load_suite(path: Path) -> SuiteSpec:
    suite_yaml = path / "suite.yaml" if path.is_dir() else path
    data = load_yaml(suite_yaml)
    if path.is_dir():
        data.setdefault("name", path.name)
    return SuiteSpec.model_validate(data)


def load_treatment(path: Path) -> TreatmentSpec:
    treatment_yaml = path / "treatment.yaml" if path.is_dir() else path
    data = load_yaml(treatment_yaml)
    if path.is_dir():
        data.setdefault("name", path.name)
    return TreatmentSpec.model_validate(data)


def load_experiment(path: Path) -> ExperimentSpec:
    data = load_yaml(path)
    data.setdefault("name", path.stem)
    return ExperimentSpec.model_validate(data)


def resolve_experiment_paths(experiment: ExperimentSpec, root: Path | None = None) -> ResolvedPaths:
    root = find_repo_root(root)
    suite_dir = resolve_named_dir(root, "suites", experiment.suite)
    baseline_dir = resolve_named_dir(root, "treatments", experiment.baseline)
    treatment_dir = resolve_named_dir(root, "treatments", experiment.treatment)
    output_dir = (root / experiment.output_dir / experiment.name).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return ResolvedPaths(
        root=root,
        suite_dir=suite_dir,
        baseline_dir=baseline_dir,
        treatment_dir=treatment_dir,
        output_dir=output_dir,
    )

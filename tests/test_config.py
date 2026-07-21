from pathlib import Path

from skill_token_bench.config import (
    find_repo_root,
    load_experiment,
    load_suite,
    load_treatment,
    resolve_experiment_paths,
)


ROOT = find_repo_root(Path(__file__))


def test_find_repo_root():
    assert (ROOT / "pyproject.toml").exists()
    assert (ROOT / "benchmarks").exists()


def test_load_suite_and_treatments():
    suite = load_suite(ROOT / "benchmarks" / "suites" / "simple-prompts")
    assert suite.name == "simple-prompts"
    assert len(suite.tasks) >= 3

    none = load_treatment(ROOT / "benchmarks" / "treatments" / "none")
    assert none.kind.value == "none"

    skill = load_treatment(ROOT / "benchmarks" / "treatments" / "i-have-adhd")
    assert skill.kind.value == "skill"


def test_resolve_experiment():
    exp = load_experiment(ROOT / "benchmarks" / "experiments" / "haiku-i-have-adhd.yaml")
    paths = resolve_experiment_paths(exp, ROOT)
    assert paths.suite_dir.name == "prompt-to-coding"
    assert paths.treatment_dir.name == "i-have-adhd"

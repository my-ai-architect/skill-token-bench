from pathlib import Path

from skill_token_bench.config import find_repo_root
from skill_token_bench.harness import run_experiment


ROOT = find_repo_root(Path(__file__))


def test_run_haiku_i_have_adhd_mock(tmp_path, monkeypatch):
    # Redirect results into tmp via experiment copy
    src = ROOT / "benchmarks" / "experiments" / "haiku-i-have-adhd.yaml"
    text = src.read_text(encoding="utf-8")
    text = text.replace("output_dir: results", f"output_dir: {tmp_path}")
    exp_path = tmp_path / "exp.yaml"
    exp_path.write_text(text, encoding="utf-8")

    report = run_experiment(exp_path, root=ROOT, fetch_remote=False, use_docker=False)
    assert report.baseline_summary.runs > 0
    assert report.treatment_summary.runs > 0
    # Skill should reduce mean output tokens on this suite
    assert report.delta.output_tokens_delta < 0
    assert (Path(report.artifacts_dir) / "report.json").exists()
    assert (Path(report.artifacts_dir) / "report.md").exists()

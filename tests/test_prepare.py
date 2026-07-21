from pathlib import Path

from skill_token_bench.config import find_repo_root, load_treatment
from skill_token_bench.treatments import prepare_treatment


ROOT = find_repo_root(Path(__file__))


def test_prepare_skill_uses_fixture(tmp_path):
    tdir = ROOT / "benchmarks" / "treatments" / "i-have-adhd"
    spec = load_treatment(tdir)
    prepared = prepare_treatment(spec, tdir, tmp_path / "stage", fetch_remote=False)
    assert prepared.skill_dir is not None
    assert (prepared.skill_dir / "SKILL.md").exists()


def test_prepare_rtk_wrappers(tmp_path):
    tdir = ROOT / "benchmarks" / "treatments" / "rtk"
    spec = load_treatment(tdir)
    prepared = prepare_treatment(spec, tdir, tmp_path / "stage", fetch_remote=False)
    assert prepared.bin_dir is not None
    assert (prepared.bin_dir / "rtk").exists()
    assert (prepared.bin_dir / "pytest").exists()

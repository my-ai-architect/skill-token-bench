"""Materialize a treatment into a run directory (clone skill, stage CLI wrapper, etc.)."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from skill_token_bench.models import TreatmentKind, TreatmentSpec


@dataclass
class PreparedTreatment:
    spec: TreatmentSpec
    root: Path
    skill_dir: Path | None = None
    bin_dir: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def prepare_treatment(
    spec: TreatmentSpec,
    treatment_dir: Path,
    staging_dir: Path,
    fetch_remote: bool = True,
) -> PreparedTreatment:
    staging_dir.mkdir(parents=True, exist_ok=True)
    prepared = PreparedTreatment(spec=spec, root=staging_dir, env=dict(spec.env))

    if spec.kind == TreatmentKind.NONE:
        prepared.notes.append("baseline: no treatment")
        return prepared

    if spec.kind == TreatmentKind.SKILL:
        skill_dir = staging_dir / "skill"
        _materialize_source(spec, treatment_dir, skill_dir, fetch_remote=fetch_remote)
        # Prefer nested skill_path when provided (e.g. skills/i-have-adhd).
        if spec.skill_path:
            candidate = skill_dir / spec.skill_path
            if candidate.exists():
                skill_dir = candidate
        prepared.skill_dir = skill_dir
        prepared.notes.append(f"skill staged at {skill_dir}")
        return prepared

    if spec.kind == TreatmentKind.CLI_INTERCEPT:
        bin_dir = staging_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        _stage_cli_intercept(spec, treatment_dir, bin_dir)
        prepared.bin_dir = bin_dir
        prepared.env["PATH"] = f"{bin_dir}:$PATH"
        prepared.env["STB_CLI_INTERCEPT"] = spec.name
        prepared.notes.append(
            f"cli intercept '{spec.name}' wrapping: {', '.join(spec.wrap_commands) or '(none)'}"
        )
        return prepared

    if spec.kind == TreatmentKind.MEMORY:
        mem_dir = staging_dir / "memory"
        _materialize_source(spec, treatment_dir, mem_dir, fetch_remote=fetch_remote)
        prepared.env["STB_MEMORY_DIR"] = str(mem_dir)
        prepared.env["STB_MEMORY_PLUGIN"] = spec.name
        prepared.notes.append(f"memory plugin staged at {mem_dir}")
        # Optional local install hooks (documented; not always runnable offline).
        for cmd in spec.install_commands:
            prepared.notes.append(f"install hint: {cmd}")
        return prepared

    if spec.kind == TreatmentKind.CUSTOM:
        custom = staging_dir / "custom"
        _materialize_source(spec, treatment_dir, custom, fetch_remote=fetch_remote)
        prepared.notes.append(f"custom treatment staged at {custom}")
        return prepared

    raise ValueError(f"Unsupported treatment kind: {spec.kind}")


def _materialize_source(
    spec: TreatmentSpec,
    treatment_dir: Path,
    dest: Path,
    fetch_remote: bool,
) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # Local fixture bundled with the treatment definition always wins for demos/tests.
    local_fixture = treatment_dir / "fixture"
    if local_fixture.exists():
        shutil.copytree(local_fixture, dest, dirs_exist_ok=True)
        return

    source = spec.source
    if source and source.local:
        src = Path(source.local)
        if not src.is_absolute():
            src = treatment_dir / src
        if src.exists():
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest / src.name)
            return

    if source and source.git and fetch_remote:
        _git_sparse_checkout(source.git, source.ref, source.path, dest)
        return

    # Placeholder marker so Docker mounts still work offline.
    (dest / "README.stb.md").write_text(
        f"# {spec.name}\n\nSource not fetched. Provide fixture/ or enable network fetch.\n",
        encoding="utf-8",
    )


def _git_sparse_checkout(url: str, ref: str, subpath: str | None, dest: Path) -> None:
    staging = dest.parent / f".git-{dest.name}"
    if staging.exists():
        shutil.rmtree(staging)
    cmd = ["git", "clone", "--depth", "1", "--branch", ref, url, str(staging)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    src = staging / subpath if subpath else staging
    if not src.exists():
        raise FileNotFoundError(f"{subpath} not found in {url}@{ref}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    shutil.rmtree(staging, ignore_errors=True)


def _stage_cli_intercept(spec: TreatmentSpec, treatment_dir: Path, bin_dir: Path) -> None:
    """Install wrapper scripts that simulate / invoke an intercept like rtk."""
    wrapper_src = treatment_dir / "wrappers"
    if wrapper_src.is_dir():
        for item in wrapper_src.iterdir():
            target = bin_dir / item.name
            shutil.copy2(item, target)
            target.chmod(0o755)
        return

    # Generic shim: logs invocation and optionally compresses stdout when STB_MOCK_RTK=1.
    shim = bin_dir / (spec.binary or "rtk")
    shim.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
# skill-token-bench CLI intercept shim
REAL_CMD="${1:-}"
shift || true
if [[ -z "${REAL_CMD}" ]]; then
  echo "usage: $(basename "$0") <command> [args...]" >&2
  exit 2
fi
TMP=$(mktemp)
if command -v "$REAL_CMD" >/dev/null 2>&1; then
  "$REAL_CMD" "$@" >"$TMP" 2>&1 || status=$?
else
  printf 'mock output for %s %s\\n' "$REAL_CMD" "$*" >"$TMP"
  status=0
fi
status=${status:-0}
if [[ "${STB_MOCK_RTK:-}" == "1" ]]; then
  # Keep head + error-looking lines — stand-in for rtk compression.
  { head -n 20 "$TMP"; grep -Ei 'error|fail|warning' "$TMP" || true; } | head -n 40
else
  cat "$TMP"
fi
rm -f "$TMP"
exit "$status"
""",
        encoding="utf-8",
    )
    shim.chmod(0o755)

    for cmd_name in spec.wrap_commands:
        link = bin_dir / cmd_name
        link.write_text(
            f'#!/usr/bin/env bash\nexec "{shim}" "{cmd_name}" "$@"\n',
            encoding="utf-8",
        )
        link.chmod(0o755)

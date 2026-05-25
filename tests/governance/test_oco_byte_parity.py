"""Byte-identical OCO migration parity gate tests.

The checked-in fixture is synthetic and only proves the comparator mechanics.
Production OCO byte parity remains xfailed until Phase 1g writes real artifacts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REF_DIR = Path("tests/governance/fixtures/synthetic_oco_reference/EURUSD_2026-05")
SCRIPT = Path("scripts/governance/validate_oco_migration_parity.py")


@pytest.mark.xfail(
    strict=True,
    reason="Phase 1g has not wired orchestrator output generation into the parity gate.",
)
def test_oco_reference_snapshot_byte_identical_after_phase_1g(tmp_path: Path) -> None:
    subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(SCRIPT),
            "--ref-dir",
            str(REF_DIR),
            "--out-dir",
            str(tmp_path),
        ],
        check=True,
    )


def test_parity_script_reports_missing_candidate_artifacts(tmp_path: Path) -> None:
    ref_dir = tmp_path / "ref"
    out_dir = tmp_path / "out"
    ref_dir.mkdir()
    (ref_dir / "state_schedule.csv").write_bytes(b"symbol,month\nEURUSD,2026-05\n")

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(SCRIPT),
            "--ref-dir",
            str(ref_dir),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "MISSING:" in result.stderr
    assert "state_schedule.csv" in result.stderr


def test_parity_script_reports_diff_candidate_artifacts(tmp_path: Path) -> None:
    ref_dir = tmp_path / "ref"
    out_dir = tmp_path / "out"
    ref_dir.mkdir()
    out_dir.mkdir()
    (ref_dir / "state_schedule.csv").write_bytes(b"symbol,month\nEURUSD,2026-05\n")
    (out_dir / "state_schedule.csv").write_bytes(b"symbol,month\nEURUSD,2026-06\n")

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(SCRIPT),
            "--ref-dir",
            str(ref_dir),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "DIFF:" in result.stderr
    assert "state_schedule.csv" in result.stderr


def test_parity_script_accepts_byte_identical_candidate_artifacts(tmp_path: Path) -> None:
    ref_dir = tmp_path / "ref"
    out_dir = tmp_path / "out"
    ref_dir.mkdir()
    out_dir.mkdir()
    artifact_bytes = b"symbol,month\nEURUSD,2026-05\n"
    (ref_dir / "state_schedule.csv").write_bytes(artifact_bytes)
    (out_dir / "state_schedule.csv").write_bytes(artifact_bytes)

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(SCRIPT),
            "--ref-dir",
            str(ref_dir),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "byte-identical" in result.stdout
    assert result.stderr == ""

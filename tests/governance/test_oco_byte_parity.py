"""OCO migration parity gate tests.

The checked-in fixture is synthetic and only proves the comparator mechanics.
Production OCO byte parity remains xfailed until real frozen artifacts are available.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REF_DIR = Path("tests/governance/fixtures/synthetic_oco_reference/EURUSD_2026-05")
SCRIPT = Path("scripts/governance/validate_oco_migration_parity.py")


@pytest.mark.xfail(
    strict=True,
    reason="raw byte parity needs real frozen artifacts; semantic parity is the Phase 1g gate",
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


def test_parity_script_accepts_semantically_equivalent_csv_and_json(tmp_path: Path) -> None:
    ref_dir = tmp_path / "ref"
    out_dir = tmp_path / "out"
    ref_dir.mkdir()
    out_dir.mkdir()
    (ref_dir / "state_schedule.csv").write_text(
        "state_id,month,selected,mean_realized_pips\n"
        "s2,2026-05,false,0.0\n"
        "s1,2026-05,true,0.300000000000\n",
        encoding="utf-8",
    )
    (out_dir / "state_schedule.csv").write_text(
        "month,selected,mean_realized_pips,state_id\n"
        "2026-05,True,0.3000000000004,s1\n"
        "2026-05,False,0,s2\n",
        encoding="utf-8",
    )
    (ref_dir / "freeze.json").write_text(
        '{"family":"oco_first_touch","model_month":"2026-05",'
        '"qualified_states":[{"state_id":"s1","verdict":"GO"}],'
        '"schema_version":"oco_v4.0","symbol":"EURUSD"}',
        encoding="utf-8",
    )
    (out_dir / "freeze.json").write_text(
        '{\n'
        '  "symbol": "EURUSD",\n'
        '  "schema_version": "oco_v4.0",\n'
        '  "qualified_states": [{"verdict": "GO", "state_id": "s1"}],\n'
        '  "model_month": "2026-05",\n'
        '  "family": "oco_first_touch"\n'
        '}',
        encoding="utf-8",
    )

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
            "--mode",
            "semantic",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "semantically equivalent" in result.stdout


def test_parity_script_reports_semantic_csv_value_diff(tmp_path: Path) -> None:
    ref_dir = tmp_path / "ref"
    out_dir = tmp_path / "out"
    ref_dir.mkdir()
    out_dir.mkdir()
    (ref_dir / "state_schedule.csv").write_text(
        "state_id,month,selected\ns1,2026-05,true\n",
        encoding="utf-8",
    )
    (out_dir / "state_schedule.csv").write_text(
        "state_id,month,selected\ns1,2026-05,false\n",
        encoding="utf-8",
    )

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
            "--mode",
            "semantic",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "SEMANTIC_DIFF:" in result.stderr
    assert "state_schedule.csv" in result.stderr


def test_parity_script_accepts_semantically_equivalent_empty_csv_artifacts(
    tmp_path: Path,
) -> None:
    ref_dir = tmp_path / "ref"
    out_dir = tmp_path / "out"
    ref_dir.mkdir()
    out_dir.mkdir()
    (ref_dir / "state_schedule.csv").write_text("\n", encoding="utf-8")
    (out_dir / "state_schedule.csv").write_text("", encoding="utf-8")

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
            "--mode",
            "semantic",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "semantically equivalent" in result.stdout

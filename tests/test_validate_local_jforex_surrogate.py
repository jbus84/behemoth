from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_lock(
    lock_dir: Path,
    symbol: str,
    *,
    deployable: bool,
    reason: str = "",
) -> None:
    payload = {
        "schema_version": 3,
        "symbol": symbol,
        "bundle": {
            "family": "oco_first_touch",
        },
        "deployability": {
            "live_deployable": deployable,
        },
        "artifacts": {},
    }
    (lock_dir / f"{symbol.lower()}_oco_first_touch_live_lock.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_build_artifacts_marks_non_deployable_symbols_as_nogo(tmp_path: Path) -> None:
    from scripts.validate_local_jforex_surrogate import build_artifacts

    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    _write_lock(lock_dir, "USDCAD", deployable=False, reason="no_gate_states")

    summary, checks = build_artifacts(
        symbols=["USDCAD"],
        lock_dir=lock_dir,
        local_signal_summary_glob="",
        local_execution_summary_glob="",
        local_lifecycle_summary_glob="",
        local_operational_summary_glob="",
        local_outcome_summary_glob="",
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        report_out=tmp_path / "report.md",
    )

    row = summary.iloc[0]
    assert row["symbol"] == "USDCAD"
    assert bool(row["historical_deployable"]) is False
    assert bool(row["local_jforex_surrogate_pass"]) is False
    assert bool(row["local_jforex_surrogate_no_go"]) is True
    assert row["verdict"] == "NO_GO"
    assert "STAGE12_API_PARITY_PASS" not in set(checks["check_id"])


def test_build_artifacts_treats_zero_lock_idle_windows_as_execution_pass(tmp_path: Path) -> None:
    from scripts.validate_local_jforex_surrogate import build_artifacts

    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    _write_lock(lock_dir, "EURUSD", deployable=True)

    _write_csv(
        tmp_path / "EURUSD_local_jforex_signal_parity_summary.csv",
        ["symbol", "jforex_signal_parity_pass"],
        [{"symbol": "EURUSD", "jforex_signal_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_local_jforex_execution_parity_summary.csv",
        ["symbol", "jforex_execution_parity_pass", "governance_selected_signal_count", "submitted_orders"],
        [
            {
                "symbol": "EURUSD",
                "jforex_execution_parity_pass": False,
                "governance_selected_signal_count": 0,
                "submitted_orders": 0,
            }
        ],
    )
    _write_csv(
        tmp_path / "EURUSD_local_jforex_execution_lifecycle_summary.csv",
        ["symbol", "execution_lifecycle_pass"],
        [{"symbol": "EURUSD", "execution_lifecycle_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_local_jforex_operational_ready_summary.csv",
        ["symbol", "operational_ready_pass"],
        [{"symbol": "EURUSD", "operational_ready_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_local_jforex_outcome_parity_summary.csv",
        ["symbol", "jforex_outcome_parity_pass"],
        [{"symbol": "EURUSD", "jforex_outcome_parity_pass": True}],
    )

    summary, checks = build_artifacts(
        symbols=["EURUSD"],
        lock_dir=lock_dir,
        local_signal_summary_glob=str(tmp_path / "*_local_jforex_signal_parity_summary.csv"),
        local_execution_summary_glob=str(tmp_path / "*_local_jforex_execution_parity_summary.csv"),
        local_lifecycle_summary_glob=str(
            tmp_path / "*_local_jforex_execution_lifecycle_summary.csv"
        ),
        local_operational_summary_glob=str(
            tmp_path / "*_local_jforex_operational_ready_summary.csv"
        ),
        local_outcome_summary_glob=str(tmp_path / "*_local_jforex_outcome_parity_summary.csv"),
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        report_out=tmp_path / "report.md",
    )

    row = summary.iloc[0]
    assert bool(row["historical_deployable"]) is True
    assert row["non_deployable_reason"] == ""
    assert bool(row["local_execution_parity_pass"]) is True
    assert bool(row["local_jforex_surrogate_pass"]) is True
    assert bool(row["local_jforex_surrogate_no_go"]) is False
    assert row["verdict"] == "green"

    execution_check = checks[checks["metric_name"] == "local_execution_parity_pass"].iloc[0]
    assert execution_check["status"] == "PASS"


def test_build_artifacts_falls_back_to_outcome_governance_count_for_zero_signal_windows(
    tmp_path: Path,
) -> None:
    from scripts.validate_local_jforex_surrogate import build_artifacts

    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    _write_lock(lock_dir, "USDCHF", deployable=True)

    _write_csv(
        tmp_path / "USDCHF_local_jforex_signal_parity_summary.csv",
        ["symbol", "jforex_signal_parity_pass"],
        [{"symbol": "USDCHF", "jforex_signal_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "USDCHF_local_jforex_execution_parity_summary.csv",
        ["symbol", "jforex_execution_parity_pass", "submitted_orders", "execution_failures"],
        [
            {
                "symbol": "USDCHF",
                "jforex_execution_parity_pass": False,
                "submitted_orders": 0,
                "execution_failures": 0,
            }
        ],
    )
    _write_csv(
        tmp_path / "USDCHF_local_jforex_execution_lifecycle_summary.csv",
        ["symbol", "execution_lifecycle_pass"],
        [{"symbol": "USDCHF", "execution_lifecycle_pass": True}],
    )
    _write_csv(
        tmp_path / "USDCHF_local_jforex_operational_ready_summary.csv",
        ["symbol", "operational_ready_pass"],
        [{"symbol": "USDCHF", "operational_ready_pass": True}],
    )
    _write_csv(
        tmp_path / "USDCHF_local_jforex_outcome_parity_summary.csv",
        ["symbol", "jforex_outcome_parity_pass", "governance_selected_signal_count"],
        [{"symbol": "USDCHF", "jforex_outcome_parity_pass": True, "governance_selected_signal_count": 0}],
    )

    summary, checks = build_artifacts(
        symbols=["USDCHF"],
        lock_dir=lock_dir,
        local_signal_summary_glob=str(tmp_path / "*_local_jforex_signal_parity_summary.csv"),
        local_execution_summary_glob=str(tmp_path / "*_local_jforex_execution_parity_summary.csv"),
        local_lifecycle_summary_glob=str(
            tmp_path / "*_local_jforex_execution_lifecycle_summary.csv"
        ),
        local_operational_summary_glob=str(
            tmp_path / "*_local_jforex_operational_ready_summary.csv"
        ),
        local_outcome_summary_glob=str(tmp_path / "*_local_jforex_outcome_parity_summary.csv"),
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        report_out=tmp_path / "report.md",
    )

    row = summary.iloc[0]
    assert bool(row["local_execution_parity_pass"]) is True
    assert bool(row["local_jforex_surrogate_pass"]) is True
    execution_check = checks[checks["metric_name"] == "local_execution_parity_pass"].iloc[0]
    assert execution_check["status"] == "PASS"
    assert execution_check["details"] == "zero-lock idle window accepted"


def test_build_artifacts_ignores_stage12_summary_input(tmp_path: Path) -> None:
    from scripts.validate_local_jforex_surrogate import build_artifacts

    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    _write_lock(lock_dir, "EURUSD", deployable=True)

    _write_csv(
        tmp_path / "ignored_stage12.csv",
        ["symbol", "stage12_api_parity_pass"],
        [{"symbol": "EURUSD", "stage12_api_parity_pass": False}],
    )
    _write_csv(
        tmp_path / "EURUSD_local_jforex_outcome_parity_summary.csv",
        ["symbol", "jforex_outcome_parity_pass"],
        [{"symbol": "EURUSD", "jforex_outcome_parity_pass": True}],
    )

    summary, checks = build_artifacts(
        symbols=["EURUSD"],
        lock_dir=lock_dir,
        local_signal_summary_glob="",
        local_execution_summary_glob="",
        local_lifecycle_summary_glob="",
        local_operational_summary_glob="",
        local_outcome_summary_glob=str(tmp_path / "*_local_jforex_outcome_parity_summary.csv"),
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        report_out=tmp_path / "report.md",
    )

    assert "STAGE12_API_PARITY_PASS" not in set(checks["check_id"])
    row = summary.iloc[0]
    assert bool(row["jforex_outcome_parity_pass"]) is True
    assert bool(row["local_jforex_surrogate_pass"]) is True

    written_summary = pd.read_csv(tmp_path / "summary.csv")
    assert "historical_deployable" in written_summary.columns
    assert "non_deployable_reason" in written_summary.columns
    assert "local_jforex_surrogate_pass" in written_summary.columns
    assert "local_jforex_surrogate_no_go" in written_summary.columns
    assert "verdict" in written_summary.columns


def test_main_rejects_legacy_stage12_cli_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from scripts.validate_local_jforex_surrogate import main

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_local_jforex_surrogate.py",
            "--stage12-summary-glob",
            str(tmp_path / "stage13_dukascopy_testclient_summary.csv"),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2

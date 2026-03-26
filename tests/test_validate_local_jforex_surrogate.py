from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd


def test_build_artifacts_marks_historical_nogo_from_lock(tmp_path: Path) -> None:
    from scripts.validate_local_jforex_surrogate import build_artifacts

    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    (lock_dir / "usdcad_oco_live_lock.json").write_text(
        json.dumps(
            {
                "symbol": "USDCAD",
                "historical_deployable": False,
                "non_deployable_reason": "no_gate_states",
            }
        ),
        encoding="utf-8",
    )

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

    assert summary.loc[0, "symbol"] == "USDCAD"
    assert summary.loc[0, "verdict"] == "nogo"
    assert bool(summary.loc[0, "local_jforex_surrogate_pass"]) is False
    assert bool(summary.loc[0, "historical_deployable"]) is False
    assert summary.loc[0, "non_deployable_reason"] == "no_gate_states"
    assert "STAGE12_API_PARITY_PASS" not in set(checks["check_id"])


def test_build_artifacts_allows_zero_lock_zero_order_window(tmp_path: Path) -> None:
    from scripts.validate_local_jforex_surrogate import build_artifacts

    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    (lock_dir / "eurusd_oco_live_lock.json").write_text(
        json.dumps({"symbol": "EURUSD", "historical_deployable": True}),
        encoding="utf-8",
    )
    execution_csv = tmp_path / "EURUSD_local_jforex_execution_parity_summary.csv"
    # This keeps the legacy execution summary red on its own; the zero-lock / zero-order
    # policy is what should override that into a surrogate pass.
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "jforex_execution_parity_pass": False,
                "locked_selected_total": 0,
                "submitted_orders": 0,
            }
        ]
    ).to_csv(execution_csv, index=False)

    summary, checks = build_artifacts(
        symbols=["EURUSD"],
        lock_dir=lock_dir,
        local_signal_summary_glob="",
        local_execution_summary_glob=str(execution_csv),
        local_lifecycle_summary_glob="",
        local_operational_summary_glob="",
        local_outcome_summary_glob="",
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        report_out=tmp_path / "report.md",
    )

    execution_row = checks[checks["metric_name"] == "local_execution_parity_pass"]
    assert len(execution_row) == 1, "local_execution_parity_pass check not found"
    assert execution_row["status"].iloc[0] == "pass"
    assert summary.loc[0, "symbol"] == "EURUSD"
    assert summary.loc[0, "verdict"] == "green"

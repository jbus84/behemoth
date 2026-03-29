from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.validate_stage13_dukascopy_testclient import build_stage13_artifacts


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_lock(path: Path, *, symbol: str, deployable: bool, reason: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "symbol": symbol,
                "historical_backtest": {
                    "deployable": deployable,
                    "non_deployable_reason": reason,
                },
            }
        )
        + "\n"
    )


def test_build_stage13_artifacts_marks_green_when_deployable_inputs_pass(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "eurusd_oco_live_lock.json", symbol="EURUSD", deployable=True)
    runtime = tmp_path / "EURUSD_jforex_runtime_events.csv"
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n")
    _write_csv(
        tmp_path / "EURUSD_jforex_signal.csv",
        [{"symbol": "EURUSD", "jforex_signal_parity_pass": True, "predict_cycles": 3}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_operational.csv",
        [{"symbol": "EURUSD", "operational_ready_pass": True}],
    )

    summary, checks = build_stage13_artifacts(
        symbols=["EURUSD"],
        lock_dir=tmp_path / "locks",
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_operational.csv"),
        reconcile_dir=tmp_path,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "historical_deployable"]) is True
    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is True
    assert summary.loc[0, "verdict"] == "green"
    assert int(summary.loc[0, "missing_inputs"]) == 0
    assert len(checks) == 3


def test_build_stage13_artifacts_allows_non_deployable_symbol_without_signal_cycles(
    tmp_path: Path,
) -> None:
    _write_lock(
        tmp_path / "locks" / "usdcad_oco_live_lock.json",
        symbol="USDCAD",
        deployable=False,
        reason="no_gate_states",
    )
    runtime = tmp_path / "USDCAD_jforex_runtime_events.csv"
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n")
    _write_csv(
        tmp_path / "USDCAD_jforex_operational.csv",
        [{"symbol": "USDCAD", "operational_ready_pass": True}],
    )

    summary, checks = build_stage13_artifacts(
        symbols=["USDCAD"],
        lock_dir=tmp_path / "locks",
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_operational.csv"),
        reconcile_dir=tmp_path,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "historical_deployable"]) is False
    assert summary.loc[0, "non_deployable_reason"] == "no_gate_states"
    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is True
    signal_check = checks[checks["metric_name"] == "dukascopy_signal_path_exercised_pass"]
    assert signal_check.iloc[0]["status"] == "pass"
    assert "non-deployable" in signal_check.iloc[0]["details"]


def test_build_stage13_artifacts_fails_when_deployable_symbol_has_no_signal_path(
    tmp_path: Path,
) -> None:
    _write_lock(tmp_path / "locks" / "gbpusd_oco_live_lock.json", symbol="GBPUSD", deployable=True)
    runtime = tmp_path / "GBPUSD_jforex_runtime_events.csv"
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n")
    _write_csv(
        tmp_path / "GBPUSD_jforex_operational.csv",
        [{"symbol": "GBPUSD", "operational_ready_pass": True}],
    )

    summary, checks = build_stage13_artifacts(
        symbols=["GBPUSD"],
        lock_dir=tmp_path / "locks",
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_operational.csv"),
        reconcile_dir=tmp_path,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "historical_deployable"]) is True
    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is False
    failed = checks[checks["status"] == "fail"]
    assert len(failed) == 1
    assert failed.iloc[0]["metric_name"] == "dukascopy_signal_path_exercised_pass"


def test_build_stage13_artifacts_fails_when_runtime_events_missing(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "usdjpy_oco_live_lock.json", symbol="USDJPY", deployable=True)
    _write_csv(
        tmp_path / "USDJPY_jforex_signal.csv",
        [{"symbol": "USDJPY", "jforex_signal_parity_pass": True, "predict_cycles": 2}],
    )
    _write_csv(
        tmp_path / "USDJPY_jforex_operational.csv",
        [{"symbol": "USDJPY", "operational_ready_pass": True}],
    )

    summary, checks = build_stage13_artifacts(
        symbols=["USDJPY"],
        lock_dir=tmp_path / "locks",
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_operational.csv"),
        reconcile_dir=tmp_path,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is False
    failed = checks[checks["status"] == "fail"]
    assert len(failed) == 1
    assert failed.iloc[0]["metric_name"] == "dukascopy_runtime_artifacts_complete_pass"

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


def _write_stage12_summary(path: Path, *, symbol: str, passed: bool) -> None:
    _write_csv(path, [{"symbol": symbol, "stage12_api_parity_pass": passed}])


def _write_dukascopy_replay_summary(
    path: Path,
    *,
    symbol: str,
    signal_pass: bool,
    execution_pass: bool,
) -> None:
    _write_csv(
        path,
        [
            {
                "symbol": symbol,
                "dukascopy_testclient_signal_parity_pass": signal_pass,
                "dukascopy_testclient_execution_parity_pass": execution_pass,
            }
        ],
    )


def test_build_stage13_artifacts_requires_stage12_prerequisite(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "eurusd_oco_live_lock.json", symbol="EURUSD", deployable=True)
    _write_stage12_summary(tmp_path / "backtest_reconcile" / "EURUSD_stage12_api_parity_summary.csv", symbol="EURUSD", passed=False)
    _write_dukascopy_replay_summary(
        tmp_path / "backtest_reconcile" / "EURUSD_dukascopy_testclient_replay_summary.csv",
        symbol="EURUSD",
        signal_pass=True,
        execution_pass=True,
    )
    runtime = tmp_path / "backtest_reconcile" / "EURUSD_jforex_runtime_events.csv"
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n2025-07-07T00:00:00Z,EURUSD,runtime,predict_cycle,True,\n")

    summary, checks = build_stage13_artifacts(
        symbols=["EURUSD"],
        lock_dir=tmp_path / "locks",
        stage12_api_parity_summary_glob=str(tmp_path / "backtest_reconcile" / "*_stage12_api_parity_summary.csv"),
        dukascopy_testclient_replay_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_dukascopy_testclient_replay_summary.csv"
        ),
        reconcile_dir=tmp_path / "backtest_reconcile",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage12_api_parity_pass"]) is False
    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is False
    assert summary.loc[0, "verdict"] == "red"
    assert "stage12_api_parity_pass" in set(checks["metric_name"])


def test_build_stage13_artifacts_ignores_local_surrogate_summaries(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "usdcad_oco_live_lock.json", symbol="USDCAD", deployable=True)
    _write_stage12_summary(tmp_path / "backtest_reconcile" / "USDCAD_stage12_api_parity_summary.csv", symbol="USDCAD", passed=True)
    _write_dukascopy_replay_summary(
        tmp_path / "backtest_reconcile" / "USDCAD_dukascopy_testclient_replay_summary.csv",
        symbol="USDCAD",
        signal_pass=True,
        execution_pass=True,
    )
    _write_csv(
        tmp_path / "backtest_reconcile" / "USDCAD_local_jforex_signal_parity_summary.csv",
        [{"symbol": "USDCAD", "jforex_signal_parity_pass": False, "overall_pass": False}],
    )
    _write_csv(
        tmp_path / "backtest_reconcile" / "USDCAD_local_jforex_operational_ready_summary.csv",
        [{"symbol": "USDCAD", "operational_ready_pass": False, "overall_pass": False}],
    )
    runtime = tmp_path / "backtest_reconcile" / "USDCAD_jforex_runtime_events.csv"
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n2025-07-07T00:00:00Z,USDCAD,runtime,predict_cycle,True,\n")

    summary, checks = build_stage13_artifacts(
        symbols=["USDCAD"],
        lock_dir=tmp_path / "locks",
        stage12_api_parity_summary_glob=str(tmp_path / "backtest_reconcile" / "*_stage12_api_parity_summary.csv"),
        dukascopy_testclient_replay_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_dukascopy_testclient_replay_summary.csv"
        ),
        reconcile_dir=tmp_path / "backtest_reconcile",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is True
    assert not any("local_jforex" in str(path) for path in checks["source_path"])
    assert "stage12_api_parity_pass" in set(checks["metric_name"])
    assert "dukascopy_testclient_signal_parity_pass" in set(checks["metric_name"])
    assert "dukascopy_testclient_execution_parity_pass" in set(checks["metric_name"])


def test_build_stage13_artifacts_treats_execution_parity_as_direct_gate(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "gbpusd_oco_live_lock.json", symbol="GBPUSD", deployable=True)
    _write_stage12_summary(tmp_path / "backtest_reconcile" / "GBPUSD_stage12_api_parity_summary.csv", symbol="GBPUSD", passed=True)
    _write_dukascopy_replay_summary(
        tmp_path / "backtest_reconcile" / "GBPUSD_dukascopy_testclient_replay_summary.csv",
        symbol="GBPUSD",
        signal_pass=True,
        execution_pass=False,
    )
    runtime = tmp_path / "backtest_reconcile" / "GBPUSD_jforex_runtime_events.csv"
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n2025-07-07T00:00:00Z,GBPUSD,runtime,predict_cycle,True,\n")

    summary, checks = build_stage13_artifacts(
        symbols=["GBPUSD"],
        lock_dir=tmp_path / "locks",
        stage12_api_parity_summary_glob=str(tmp_path / "backtest_reconcile" / "*_stage12_api_parity_summary.csv"),
        dukascopy_testclient_replay_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_dukascopy_testclient_replay_summary.csv"
        ),
        reconcile_dir=tmp_path / "backtest_reconcile",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage12_api_parity_pass"]) is True
    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is False
    failed = checks[checks["status"] == "fail"]
    assert len(failed) == 1
    assert failed.iloc[0]["metric_name"] == "dukascopy_testclient_execution_parity_pass"


def test_build_stage13_artifacts_prefers_explicit_replay_over_fallback_summaries(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "audusd_oco_live_lock.json", symbol="AUDUSD", deployable=True)
    _write_stage12_summary(tmp_path / "backtest_reconcile" / "AUDUSD_stage12_api_parity_summary.csv", symbol="AUDUSD", passed=True)
    _write_dukascopy_replay_summary(
        tmp_path / "backtest_reconcile" / "AUDUSD_dukascopy_testclient_replay_summary.csv",
        symbol="AUDUSD",
        signal_pass=True,
        execution_pass=True,
    )
    _write_csv(
        tmp_path / "backtest_reconcile" / "AUDUSD_jforex_signal_parity_summary.csv",
        [{"symbol": "AUDUSD", "jforex_signal_parity_pass": False}],
    )
    _write_csv(
        tmp_path / "backtest_reconcile" / "AUDUSD_jforex_execution_parity_summary.csv",
        [{"symbol": "AUDUSD", "jforex_execution_parity_pass": False}],
    )
    runtime = tmp_path / "backtest_reconcile" / "AUDUSD_jforex_runtime_events.csv"
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n2025-07-07T00:00:00Z,AUDUSD,runtime,predict_cycle,True,\n")

    summary, checks = build_stage13_artifacts(
        symbols=["AUDUSD"],
        lock_dir=tmp_path / "locks",
        stage12_api_parity_summary_glob=str(tmp_path / "backtest_reconcile" / "*_stage12_api_parity_summary.csv"),
        dukascopy_testclient_replay_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_dukascopy_testclient_replay_summary.csv"
        ),
        dukascopy_testclient_signal_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_jforex_signal_parity_summary.csv"
        ),
        dukascopy_testclient_execution_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_jforex_execution_parity_summary.csv"
        ),
        reconcile_dir=tmp_path / "backtest_reconcile",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is True
    assert set(checks.loc[checks["metric_name"].str.contains("dukascopy_testclient_"), "source_path"]) == {
        str(tmp_path / "backtest_reconcile" / "AUDUSD_dukascopy_testclient_replay_summary.csv")
    }


def test_build_stage13_artifacts_uses_fallback_when_replay_glob_matches_nothing(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "usdchf_oco_live_lock.json", symbol="USDCHF", deployable=True)
    _write_stage12_summary(tmp_path / "backtest_reconcile" / "USDCHF_stage12_api_parity_summary.csv", symbol="USDCHF", passed=True)
    _write_csv(
        tmp_path / "backtest_reconcile" / "USDCHF_jforex_signal_parity_summary.csv",
        [{"symbol": "USDCHF", "jforex_signal_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "backtest_reconcile" / "USDCHF_jforex_execution_parity_summary.csv",
        [{"symbol": "USDCHF", "jforex_execution_parity_pass": True}],
    )
    runtime = tmp_path / "backtest_reconcile" / "USDCHF_jforex_runtime_events.csv"
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n2025-07-07T00:00:00Z,USDCHF,runtime,predict_cycle,True,\n")

    summary, checks = build_stage13_artifacts(
        symbols=["USDCHF"],
        lock_dir=tmp_path / "locks",
        stage12_api_parity_summary_glob=str(tmp_path / "backtest_reconcile" / "*_stage12_api_parity_summary.csv"),
        dukascopy_testclient_replay_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_dukascopy_testclient_replay_summary.csv"
        ),
        dukascopy_testclient_signal_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_jforex_signal_parity_summary.csv"
        ),
        dukascopy_testclient_execution_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_jforex_execution_parity_summary.csv"
        ),
        reconcile_dir=tmp_path / "backtest_reconcile",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is True
    assert set(checks.loc[checks["metric_name"].str.contains("dukascopy_testclient_"), "source_path"]) == {
        str(tmp_path / "backtest_reconcile" / "USDCHF_jforex_signal_parity_summary.csv"),
        str(tmp_path / "backtest_reconcile" / "USDCHF_jforex_execution_parity_summary.csv"),
    }


def test_build_stage13_artifacts_uses_fallback_for_partial_replay_family(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "usdjpy_oco_live_lock.json", symbol="USDJPY", deployable=True)
    _write_stage12_summary(tmp_path / "backtest_reconcile" / "USDJPY_stage12_api_parity_summary.csv", symbol="USDJPY", passed=True)
    _write_csv(
        tmp_path / "backtest_reconcile" / "USDJPY_dukascopy_testclient_replay_summary.csv",
        [{"symbol": "USDJPY", "dukascopy_testclient_signal_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "backtest_reconcile" / "USDJPY_jforex_execution_parity_summary.csv",
        [{"symbol": "USDJPY", "jforex_execution_parity_pass": True}],
    )
    runtime = tmp_path / "backtest_reconcile" / "USDJPY_jforex_runtime_events.csv"
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n2025-07-07T00:00:00Z,USDJPY,runtime,predict_cycle,True,\n")

    summary, checks = build_stage13_artifacts(
        symbols=["USDJPY"],
        lock_dir=tmp_path / "locks",
        stage12_api_parity_summary_glob=str(tmp_path / "backtest_reconcile" / "*_stage12_api_parity_summary.csv"),
        dukascopy_testclient_replay_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_dukascopy_testclient_replay_summary.csv"
        ),
        dukascopy_testclient_execution_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_jforex_execution_parity_summary.csv"
        ),
        reconcile_dir=tmp_path / "backtest_reconcile",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is True
    assert set(checks.loc[checks["metric_name"].str.contains("dukascopy_testclient_"), "source_path"]) == {
        str(tmp_path / "backtest_reconcile" / "USDJPY_dukascopy_testclient_replay_summary.csv"),
        str(tmp_path / "backtest_reconcile" / "USDJPY_jforex_execution_parity_summary.csv"),
    }


def test_build_stage13_artifacts_reports_missing_inputs_with_expected_source_paths(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "eurusd_oco_live_lock.json", symbol="EURUSD", deployable=True)
    runtime = tmp_path / "backtest_reconcile" / "EURUSD_jforex_runtime_events.csv"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n2025-07-07T00:00:00Z,EURUSD,runtime,predict_cycle,True,\n")

    summary, checks = build_stage13_artifacts(
        symbols=["EURUSD"],
        lock_dir=tmp_path / "locks",
        stage12_api_parity_summary_glob=str(tmp_path / "backtest_reconcile" / "*_stage12_api_parity_summary.csv"),
        dukascopy_testclient_replay_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_dukascopy_testclient_replay_summary.csv"
        ),
        reconcile_dir=tmp_path / "backtest_reconcile",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is False

    stage12_check = checks[checks["metric_name"] == "stage12_api_parity_pass"].iloc[0]
    signal_check = checks[checks["metric_name"] == "dukascopy_testclient_signal_parity_pass"].iloc[0]
    execution_check = checks[checks["metric_name"] == "dukascopy_testclient_execution_parity_pass"].iloc[0]

    assert stage12_check["source_path"].endswith("EURUSD_stage12_api_parity_summary.csv")
    assert stage12_check["details"] == "missing Stage 12 API parity summary: " + stage12_check["source_path"]
    assert signal_check["source_path"].endswith("EURUSD_dukascopy_testclient_replay_summary.csv")
    assert signal_check["details"] == "missing Dukascopy/TestClient signal parity summary: " + signal_check["source_path"]
    assert execution_check["source_path"].endswith("EURUSD_dukascopy_testclient_replay_summary.csv")
    assert execution_check["details"] == "missing Dukascopy/TestClient execution parity summary: " + execution_check["source_path"]


def test_build_stage13_artifacts_reports_runtime_artifact_as_current_dukascopy_surface(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "gbpusd_oco_live_lock.json", symbol="GBPUSD", deployable=True)
    _write_stage12_summary(tmp_path / "backtest_reconcile" / "GBPUSD_stage12_api_parity_summary.csv", symbol="GBPUSD", passed=True)
    _write_dukascopy_replay_summary(
        tmp_path / "backtest_reconcile" / "GBPUSD_dukascopy_testclient_replay_summary.csv",
        symbol="GBPUSD",
        signal_pass=True,
        execution_pass=True,
    )

    summary, checks = build_stage13_artifacts(
        symbols=["GBPUSD"],
        lock_dir=tmp_path / "locks",
        stage12_api_parity_summary_glob=str(tmp_path / "backtest_reconcile" / "*_stage12_api_parity_summary.csv"),
        dukascopy_testclient_replay_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_dukascopy_testclient_replay_summary.csv"
        ),
        reconcile_dir=tmp_path / "backtest_reconcile",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "dukascopy_runtime_artifacts_complete_pass"]) is False
    runtime_check = checks[checks["metric_name"] == "dukascopy_runtime_artifacts_complete_pass"].iloc[0]
    assert runtime_check["source_path"].endswith("GBPUSD_jforex_runtime_events.csv")
    assert "current Dukascopy replay runtime-events artifact" in runtime_check["details"]
    assert "legacy filename retained" in runtime_check["details"]


def test_build_stage13_artifacts_rejects_header_only_runtime_events_artifact(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "eurusd_oco_live_lock.json", symbol="EURUSD", deployable=True)
    _write_stage12_summary(
        tmp_path / "backtest_reconcile" / "EURUSD_stage12_api_parity_summary.csv",
        symbol="EURUSD",
        passed=True,
    )
    _write_dukascopy_replay_summary(
        tmp_path / "backtest_reconcile" / "EURUSD_dukascopy_testclient_replay_summary.csv",
        symbol="EURUSD",
        signal_pass=True,
        execution_pass=True,
    )
    runtime = tmp_path / "backtest_reconcile" / "EURUSD_jforex_runtime_events.csv"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("event_name,pass\n")

    summary, checks = build_stage13_artifacts(
        symbols=["EURUSD"],
        lock_dir=tmp_path / "locks",
        stage12_api_parity_summary_glob=str(tmp_path / "backtest_reconcile" / "*_stage12_api_parity_summary.csv"),
        dukascopy_testclient_replay_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_dukascopy_testclient_replay_summary.csv"
        ),
        reconcile_dir=tmp_path / "backtest_reconcile",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "dukascopy_runtime_artifacts_complete_pass"]) is False
    runtime_check = checks[checks["metric_name"] == "dukascopy_runtime_artifacts_complete_pass"].iloc[0]
    assert runtime_check["status"] == "fail"


def test_build_stage13_artifacts_keeps_primary_summary_contract_minimal(tmp_path: Path) -> None:
    _write_lock(tmp_path / "locks" / "audusd_oco_live_lock.json", symbol="AUDUSD", deployable=True)
    _write_stage12_summary(tmp_path / "backtest_reconcile" / "AUDUSD_stage12_api_parity_summary.csv", symbol="AUDUSD", passed=True)
    _write_dukascopy_replay_summary(
        tmp_path / "backtest_reconcile" / "AUDUSD_dukascopy_testclient_replay_summary.csv",
        symbol="AUDUSD",
        signal_pass=True,
        execution_pass=True,
    )
    runtime = tmp_path / "backtest_reconcile" / "AUDUSD_jforex_runtime_events.csv"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n2025-07-07T00:00:00Z,AUDUSD,runtime,predict_cycle,True,\n")

    summary, _checks = build_stage13_artifacts(
        symbols=["AUDUSD"],
        lock_dir=tmp_path / "locks",
        stage12_api_parity_summary_glob=str(tmp_path / "backtest_reconcile" / "*_stage12_api_parity_summary.csv"),
        dukascopy_testclient_replay_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_dukascopy_testclient_replay_summary.csv"
        ),
        reconcile_dir=tmp_path / "backtest_reconcile",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert list(summary.columns) == [
        "symbol",
        "dukascopy_runtime_artifacts_complete_pass",
        "stage12_api_parity_pass",
        "dukascopy_testclient_signal_parity_pass",
        "dukascopy_testclient_execution_parity_pass",
        "stage13_dukascopy_testclient_pass",
        "missing_inputs",
        "verdict",
        "evaluated_at_utc",
    ]


def test_build_stage13_artifacts_does_not_bypass_signal_parity_for_non_deployable_symbols(
    tmp_path: Path,
) -> None:
    _write_lock(
        tmp_path / "locks" / "usdcad_oco_live_lock.json",
        symbol="USDCAD",
        deployable=False,
        reason="historically non-deployable",
    )
    _write_stage12_summary(
        tmp_path / "backtest_reconcile" / "USDCAD_stage12_api_parity_summary.csv",
        symbol="USDCAD",
        passed=True,
    )
    runtime = tmp_path / "backtest_reconcile" / "USDCAD_jforex_runtime_events.csv"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text("event_ts_utc,symbol,category,event_name,pass,detail\n2025-07-07T00:00:00Z,USDCAD,runtime,predict_cycle,True,\n")

    summary, checks = build_stage13_artifacts(
        symbols=["USDCAD"],
        lock_dir=tmp_path / "locks",
        stage12_api_parity_summary_glob=str(tmp_path / "backtest_reconcile" / "*_stage12_api_parity_summary.csv"),
        dukascopy_testclient_replay_summary_glob=str(
            tmp_path / "backtest_reconcile" / "*_dukascopy_testclient_replay_summary.csv"
        ),
        reconcile_dir=tmp_path / "backtest_reconcile",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is False
    signal_check = checks[checks["metric_name"] == "dukascopy_testclient_signal_parity_pass"].iloc[0]
    assert bool(signal_check["metric_value"]) is False
    assert "non-deployable historical month" not in str(signal_check["details"])
    assert signal_check["details"] == (
        "missing Dukascopy/TestClient signal parity summary: "
        + signal_check["source_path"]
    )

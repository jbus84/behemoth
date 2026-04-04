from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from scripts.validate_stage14_jforex_runtime_certification import build_stage14_artifacts


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _utc_str(offset_days: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_local_surrogate_row(
    tmp_path: Path,
    symbol: str,
    *,
    historical_deployable: bool,
    non_deployable_reason: str = "",
    verdict: str | None = None,
    local_jforex_surrogate_pass: bool | None = None,
) -> Path:
    row: dict[str, object] = {
        "symbol": symbol,
        "historical_deployable": historical_deployable,
        "non_deployable_reason": non_deployable_reason,
    }
    if verdict is not None:
        row["verdict"] = verdict
    if local_jforex_surrogate_pass is not None:
        row["local_jforex_surrogate_pass"] = local_jforex_surrogate_pass
    path = tmp_path / f"{symbol}_local_jforex_surrogate.csv"
    _write_csv(path, [row])
    return path


def _write_stage14_green_inputs(tmp_path: Path, symbol: str) -> None:
    for name, col in [
        ("stage13", "stage13_dukascopy_testclient_pass"),
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("jforex_lifecycle", "execution_lifecycle_pass"),
        ("jforex_ops", "operational_ready_pass"),
        ("outcome", "jforex_outcome_parity_pass"),
    ]:
        _write_csv(tmp_path / f"{symbol}_{name}.csv", [{"symbol": symbol, col: True}])


def _write_runtime_events(path: Path, symbol: str) -> None:
    path.write_text(
        "event_ts_utc,symbol,category,event_name,pass,detail\n"
        f"2026-04-03T10:00:00Z,{symbol},signal,predict_cycle,true,close_ts=2026-04-03T10:00:00Z\n",
        encoding="utf-8",
    )


def test_build_stage14_artifacts_marks_green_when_all_checks_pass(tmp_path: Path) -> None:
    _write_runtime_events(tmp_path / "EURUSD_jforex_runtime_events.csv", "EURUSD")
    _write_runtime_events(tmp_path / "EURUSD_local_jforex_runtime_events.csv", "EURUSD")
    _write_csv(
        tmp_path / "EURUSD_stage13.csv",
        [{"symbol": "EURUSD", "stage13_dukascopy_testclient_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_signal.csv",
        [{"symbol": "EURUSD", "jforex_signal_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_execution.csv",
        [{"symbol": "EURUSD", "jforex_execution_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_lifecycle.csv",
        [{"symbol": "EURUSD", "execution_lifecycle_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_ops.csv",
        [{"symbol": "EURUSD", "operational_ready_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_outcome.csv",
        [{"symbol": "EURUSD", "jforex_outcome_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "local_surrogate.csv",
        [{"symbol": "EURUSD", "local_jforex_surrogate_pass": True}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is True
    assert summary.loc[0, "verdict"] == "green"
    assert int(summary.loc[0, "missing_inputs"]) == 0
    assert len(checks) == 7


def test_build_stage14_artifacts_writes_recurring_session_wording(tmp_path: Path) -> None:
    _write_runtime_events(tmp_path / "EURUSD_jforex_runtime_events.csv", "EURUSD")
    _write_runtime_events(tmp_path / "EURUSD_local_jforex_runtime_events.csv", "EURUSD")
    _write_stage14_green_inputs(tmp_path, "EURUSD")
    _write_csv(
        tmp_path / "local_surrogate.csv",
        [{"symbol": "EURUSD", "local_jforex_surrogate_pass": True}],
    )

    report_out = tmp_path / "out" / "report.md"
    snapshot_out = tmp_path / "out" / "snapshot.md"

    build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=report_out,
        snapshot_out=snapshot_out,
    )

    report_txt = report_out.read_text(encoding="utf-8")
    snapshot_txt = snapshot_out.read_text(encoding="utf-8")

    assert "single runtime certification authority" in report_txt
    assert "supervised shakedown" in report_txt
    assert "does not by itself claim recurring live certification" in report_txt
    assert "single runtime certification authority" in snapshot_txt
    assert "hard gate for the Dukascopy JForex adapter" not in snapshot_txt


def test_build_stage14_artifacts_fails_when_jforex_inputs_missing(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "GBPUSD_stage13.csv",
        [{"symbol": "GBPUSD", "stage13_dukascopy_testclient_pass": True}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["GBPUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob="",
        jforex_execution_summary_glob="",
        jforex_lifecycle_summary_glob="",
        jforex_operational_summary_glob="",
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is True
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    assert int(summary.loc[0, "missing_inputs"]) == 6
    failed = checks[checks["status"] == "fail"]
    assert len(failed) == 6


def test_build_stage14_artifacts_ignores_local_surrogate_matches(tmp_path: Path) -> None:
    _write_runtime_events(tmp_path / "GBPUSD_jforex_runtime_events.csv", "GBPUSD")
    _write_csv(
        tmp_path / "GBPUSD_stage13.csv",
        [{"symbol": "GBPUSD", "stage13_dukascopy_testclient_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_jforex_signal.csv",
        [{"symbol": "GBPUSD", "jforex_signal_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_local_jforex_signal.csv",
        [{"symbol": "GBPUSD", "jforex_signal_parity_pass": False}],
    )
    _write_csv(
        tmp_path / "GBPUSD_jforex_execution.csv",
        [{"symbol": "GBPUSD", "jforex_execution_parity_pass": False}],
    )
    _write_csv(
        tmp_path / "GBPUSD_local_jforex_execution.csv",
        [{"symbol": "GBPUSD", "jforex_execution_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_jforex_lifecycle.csv",
        [{"symbol": "GBPUSD", "execution_lifecycle_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_local_jforex_lifecycle.csv",
        [{"symbol": "GBPUSD", "execution_lifecycle_pass": False}],
    )
    _write_csv(
        tmp_path / "GBPUSD_jforex_ops.csv",
        [{"symbol": "GBPUSD", "operational_ready_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_local_jforex_ops.csv",
        [{"symbol": "GBPUSD", "operational_ready_pass": False}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["GBPUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*jforex_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "jforex_signal_parity_pass"]) is True
    assert bool(summary.loc[0, "jforex_execution_parity_pass"]) is False
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    execution_check = checks[checks["metric_name"] == "jforex_execution_parity_pass"].iloc[0]
    assert execution_check["source_path"].endswith("GBPUSD_jforex_execution.csv")


def test_build_stage14_artifacts_keeps_requested_symbol_scope(tmp_path: Path) -> None:
    _write_runtime_events(tmp_path / "GBPUSD_jforex_runtime_events.csv", "GBPUSD")
    _write_csv(
        tmp_path / "GBPUSD_stage13.csv",
        [{"symbol": "GBPUSD", "stage13_dukascopy_testclient_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_jforex_signal.csv",
        [{"symbol": "GBPUSD", "jforex_signal_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_jforex_execution.csv",
        [{"symbol": "GBPUSD", "jforex_execution_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_jforex_lifecycle.csv",
        [{"symbol": "GBPUSD", "execution_lifecycle_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_jforex_ops.csv",
        [{"symbol": "GBPUSD", "operational_ready_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_stage13.csv",
        [{"symbol": "EURUSD", "stage13_dukascopy_testclient_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_signal.csv",
        [{"symbol": "EURUSD", "jforex_signal_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_execution.csv",
        [{"symbol": "EURUSD", "jforex_execution_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_lifecycle.csv",
        [{"symbol": "EURUSD", "execution_lifecycle_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_ops.csv",
        [{"symbol": "EURUSD", "operational_ready_pass": True}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["GBPUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert summary["symbol"].tolist() == ["GBPUSD"]
    assert checks["symbol"].tolist() == ["GBPUSD"] * 7


def test_build_stage14_artifacts_includes_outcome_parity_check(tmp_path: Path) -> None:
    """Stage 14 must include jforex_outcome_parity_pass as a check."""
    _write_runtime_events(tmp_path / "EURUSD_jforex_runtime_events.csv", "EURUSD")
    _write_csv(
        tmp_path / "EURUSD_stage13.csv",
        [{"symbol": "EURUSD", "stage13_dukascopy_testclient_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_signal.csv",
        [{"symbol": "EURUSD", "jforex_signal_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_execution.csv",
        [{"symbol": "EURUSD", "jforex_execution_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_lifecycle.csv", [{"symbol": "EURUSD", "execution_lifecycle_pass": True}]
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_ops.csv", [{"symbol": "EURUSD", "operational_ready_pass": True}]
    )
    # outcome parity missing — stage14 must fail and show outcome_parity check as missing
    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    assert int(summary.loc[0, "missing_inputs"]) >= 1
    outcome_check = checks[checks["metric_name"] == "jforex_outcome_parity_pass"]
    assert len(outcome_check) == 1
    assert outcome_check.iloc[0]["status"] == "fail"


def test_build_stage14_artifacts_includes_local_surrogate_check(tmp_path: Path) -> None:
    """Stage 14 must include local_jforex_surrogate_pass as a prerequisite check."""
    _write_runtime_events(tmp_path / "EURUSD_jforex_runtime_events.csv", "EURUSD")
    _write_csv(
        tmp_path / "EURUSD_stage13.csv",
        [{"symbol": "EURUSD", "stage13_dukascopy_testclient_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_signal.csv",
        [{"symbol": "EURUSD", "jforex_signal_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_execution.csv",
        [{"symbol": "EURUSD", "jforex_execution_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_lifecycle.csv", [{"symbol": "EURUSD", "execution_lifecycle_pass": True}]
    )
    _write_csv(
        tmp_path / "EURUSD_jforex_ops.csv", [{"symbol": "EURUSD", "operational_ready_pass": True}]
    )
    _write_csv(
        tmp_path / "EURUSD_outcome.csv", [{"symbol": "EURUSD", "jforex_outcome_parity_pass": True}]
    )
    # local surrogate missing — stage14 must fail
    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob="",
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"]
    assert len(surrogate_check) == 1
    assert surrogate_check.iloc[0]["status"] == "fail"


def test_build_stage14_artifacts_accepts_local_surrogate_nogo_for_non_deployable_symbol(
    tmp_path: Path,
) -> None:
    _write_stage14_green_inputs(tmp_path, "USDCAD")
    _write_runtime_events(tmp_path / "USDCAD_jforex_runtime_events.csv", "USDCAD")
    _write_runtime_events(tmp_path / "USDCAD_local_jforex_runtime_events.csv", "USDCAD")
    local_surrogate_path = _write_local_surrogate_row(
        tmp_path,
        "USDCAD",
        historical_deployable=False,
        non_deployable_reason="no_gate_states",
        verdict="NO_GO",
    )

    summary, checks = build_stage14_artifacts(
        symbols=["USDCAD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(local_surrogate_path),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is True
    assert summary.loc[0, "verdict"] == "nogo"
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"]
    assert len(surrogate_check) == 1
    assert surrogate_check.iloc[0]["status"] == "pass"
    assert "no_go" in surrogate_check.iloc[0]["details"].lower()
    assert bool(surrogate_check.iloc[0]["metric_value"]) is True


def test_build_stage14_artifacts_marks_non_deployable_symbol_as_nogo(tmp_path: Path) -> None:
    _write_runtime_events(tmp_path / "USDCAD_jforex_runtime_events.csv", "USDCAD")
    _write_runtime_events(tmp_path / "USDCAD_local_jforex_runtime_events.csv", "USDCAD")
    _write_csv(
        tmp_path / "USDCAD_stage13.csv",
        [{"symbol": "USDCAD", "stage13_dukascopy_testclient_pass": True}],
    )
    _write_csv(
        tmp_path / "USDCAD_jforex_signal.csv",
        [{"symbol": "USDCAD", "jforex_signal_parity_pass": False}],
    )
    _write_csv(
        tmp_path / "USDCAD_jforex_execution.csv",
        [{"symbol": "USDCAD", "jforex_execution_parity_pass": False}],
    )
    _write_csv(
        tmp_path / "USDCAD_jforex_lifecycle.csv",
        [{"symbol": "USDCAD", "execution_lifecycle_pass": True}],
    )
    _write_csv(
        tmp_path / "USDCAD_jforex_ops.csv",
        [{"symbol": "USDCAD", "operational_ready_pass": True}],
    )
    _write_csv(
        tmp_path / "USDCAD_outcome.csv",
        [{"symbol": "USDCAD", "jforex_outcome_parity_pass": False}],
    )
    local_surrogate_path = _write_local_surrogate_row(
        tmp_path,
        "USDCAD",
        historical_deployable=False,
        non_deployable_reason="no_gate_states",
        verdict="NO_GO",
    )

    summary, checks = build_stage14_artifacts(
        symbols=["USDCAD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(local_surrogate_path),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    assert summary.loc[0, "verdict"] == "nogo"
    for metric_name in (
        "jforex_signal_parity_pass",
        "jforex_execution_parity_pass",
        "jforex_outcome_parity_pass",
    ):
        check = checks[checks["metric_name"] == metric_name]
        assert len(check) == 1
        assert check.iloc[0]["status"] == "nogo"
        assert "historical non-deployable" in str(check.iloc[0]["details"]).lower()
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"]
    assert len(surrogate_check) == 1
    assert surrogate_check.iloc[0]["status"] == "pass"


def test_build_stage14_artifacts_rejects_deployable_symbol_with_local_surrogate_nogo(
    tmp_path: Path,
) -> None:
    _write_stage14_green_inputs(tmp_path, "EURUSD")
    _write_runtime_events(tmp_path / "EURUSD_jforex_runtime_events.csv", "EURUSD")
    _write_runtime_events(tmp_path / "EURUSD_local_jforex_runtime_events.csv", "EURUSD")
    local_surrogate_path = _write_local_surrogate_row(
        tmp_path,
        "EURUSD",
        historical_deployable=True,
        verdict="NO_GO",
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(local_surrogate_path),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"]
    assert len(surrogate_check) == 1
    assert surrogate_check.iloc[0]["status"] == "fail"
    assert "historical_deployable" in surrogate_check.iloc[0]["details"].lower()


def test_build_stage14_artifacts_green_with_all_seven_checks(tmp_path: Path) -> None:
    """Stage 14 is green only when all 7 checks pass."""
    _write_runtime_events(tmp_path / "EURUSD_jforex_runtime_events.csv", "EURUSD")
    _write_runtime_events(tmp_path / "EURUSD_local_jforex_runtime_events.csv", "EURUSD")
    for name, col in [
        ("stage13", "stage13_dukascopy_testclient_pass"),
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("jforex_lifecycle", "execution_lifecycle_pass"),
        ("jforex_ops", "operational_ready_pass"),
        ("outcome", "jforex_outcome_parity_pass"),
    ]:
        _write_csv(tmp_path / f"EURUSD_{name}.csv", [{"symbol": "EURUSD", col: True}])
    _write_csv(
        tmp_path / "local_surrogate.csv",
        [{"symbol": "EURUSD", "local_jforex_surrogate_pass": True}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is True
    assert summary.loc[0, "verdict"] == "green"
    assert int(summary.loc[0, "missing_inputs"]) == 0
    assert len(checks) == 7


def test_build_stage14_artifacts_fails_when_input_artifact_is_stale(tmp_path: Path) -> None:
    """A Stage 14 input CSV with evaluated_at_utc older than max_artifact_age_days must fail."""
    _write_runtime_events(tmp_path / "EURUSD_jforex_runtime_events.csv", "EURUSD")
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh_ts = _utc_str()
    _write_csv(
        tmp_path / "EURUSD_stage13.csv",
        [
            {
                "symbol": "EURUSD",
                "stage13_dukascopy_testclient_pass": True,
                "evaluated_at_utc": stale_ts,
            }
        ],
    )
    for name, col in [
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("jforex_lifecycle", "execution_lifecycle_pass"),
        ("jforex_ops", "operational_ready_pass"),
    ]:
        _write_csv(
            tmp_path / f"EURUSD_{name}.csv",
            [{"symbol": "EURUSD", col: True, "evaluated_at_utc": fresh_ts}],
        )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
        reconcile_dir=tmp_path,
        max_artifact_age_days=7,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    stage13_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"]
    assert stage13_check.iloc[0]["status"] == "fail"
    assert "stale" in stage13_check.iloc[0]["details"].lower()


def test_build_stage14_artifacts_passes_when_all_fresh(tmp_path: Path) -> None:
    """Staleness check must not fire when all inputs are recent."""
    _write_runtime_events(tmp_path / "EURUSD_jforex_runtime_events.csv", "EURUSD")
    fresh_ts = _utc_str()
    for name, col in [
        ("stage13", "stage13_dukascopy_testclient_pass"),
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("jforex_lifecycle", "execution_lifecycle_pass"),
        ("jforex_ops", "operational_ready_pass"),
    ]:
        _write_csv(
            tmp_path / f"EURUSD_{name}.csv",
            [{"symbol": "EURUSD", col: True, "evaluated_at_utc": fresh_ts}],
        )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
        reconcile_dir=tmp_path,
        max_artifact_age_days=7,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    # outcome+surrogate both missing → cert fails overall, but stage13 check must be "pass" (fresh)
    stage13_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"]
    assert stage13_check.iloc[0]["status"] == "pass"
    assert stage13_check.iloc[0]["details"] == ""


def test_build_stage14_artifacts_accepts_non_deployable_local_surrogate_nogo(
    tmp_path: Path,
) -> None:
    _write_runtime_events(tmp_path / "USDCAD_jforex_runtime_events.csv", "USDCAD")
    _write_runtime_events(tmp_path / "USDCAD_local_jforex_runtime_events.csv", "USDCAD")
    for name, col in [
        ("stage13", "stage13_dukascopy_testclient_pass"),
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("jforex_lifecycle", "execution_lifecycle_pass"),
        ("jforex_ops", "operational_ready_pass"),
        ("outcome", "jforex_outcome_parity_pass"),
    ]:
        _write_csv(tmp_path / f"USDCAD_{name}.csv", [{"symbol": "USDCAD", col: True}])
    _write_csv(
        tmp_path / "local_surrogate.csv",
        [
            {
                "symbol": "USDCAD",
                "verdict": "NO_GO",
                "historical_deployable": False,
                "non_deployable_reason": "no_gate_states",
            }
        ],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["USDCAD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "local_jforex_surrogate_pass"]) is True
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is True
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"].iloc[0]
    assert surrogate_check["status"] == "pass"
    assert "non-deployable" in surrogate_check["details"].lower()
    assert "historical_deployable=false" in surrogate_check["details"].lower()
    assert "no_gate_states" in surrogate_check["details"]


def test_build_stage14_artifacts_rejects_deployable_local_surrogate_nogo(tmp_path: Path) -> None:
    _write_runtime_events(tmp_path / "EURUSD_jforex_runtime_events.csv", "EURUSD")
    _write_runtime_events(tmp_path / "EURUSD_local_jforex_runtime_events.csv", "EURUSD")
    for name, col in [
        ("stage13", "stage13_dukascopy_testclient_pass"),
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("jforex_lifecycle", "execution_lifecycle_pass"),
        ("jforex_ops", "operational_ready_pass"),
        ("outcome", "jforex_outcome_parity_pass"),
    ]:
        _write_csv(tmp_path / f"EURUSD_{name}.csv", [{"symbol": "EURUSD", col: True}])
    _write_csv(
        tmp_path / "local_surrogate.csv",
        [{"symbol": "EURUSD", "verdict": "NO_GO", "historical_deployable": True}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "local_jforex_surrogate_pass"]) is False
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"].iloc[0]
    assert surrogate_check["status"] == "fail"
    assert "historical_deployable" in surrogate_check["details"].lower()


def test_build_stage14_artifacts_requires_canonical_jforex_runtime_events_file(
    tmp_path: Path,
) -> None:
    _write_stage14_green_inputs(tmp_path, "EURUSD")
    _write_runtime_events(tmp_path / "EURUSD_local_jforex_runtime_events.csv", "EURUSD")
    _write_csv(
        tmp_path / "local_surrogate.csv",
        [{"symbol": "EURUSD", "local_jforex_surrogate_pass": True}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    outcome_check = checks[checks["metric_name"] == "jforex_outcome_parity_pass"].iloc[0]
    assert outcome_check["status"] == "fail"
    assert "EURUSD_jforex_runtime_events.csv" in outcome_check["details"]


def test_build_stage14_artifacts_requires_local_surrogate_runtime_events_file(
    tmp_path: Path,
) -> None:
    _write_stage14_green_inputs(tmp_path, "EURUSD")
    _write_runtime_events(tmp_path / "EURUSD_jforex_runtime_events.csv", "EURUSD")
    _write_csv(
        tmp_path / "local_surrogate.csv",
        [{"symbol": "EURUSD", "local_jforex_surrogate_pass": True}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"].iloc[0]
    assert surrogate_check["status"] == "fail"
    assert "EURUSD_local_jforex_runtime_events.csv" in surrogate_check["details"]


def test_build_stage14_artifacts_rejects_zero_byte_canonical_runtime_events_file(
    tmp_path: Path,
) -> None:
    _write_stage14_green_inputs(tmp_path, "EURUSD")
    (tmp_path / "EURUSD_jforex_runtime_events.csv").write_bytes(b"")
    _write_runtime_events(tmp_path / "EURUSD_local_jforex_runtime_events.csv", "EURUSD")
    _write_csv(
        tmp_path / "local_surrogate.csv",
        [{"symbol": "EURUSD", "local_jforex_surrogate_pass": True}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    assert int(summary.loc[0, "missing_inputs"]) == 1
    outcome_check = checks[checks["metric_name"] == "jforex_outcome_parity_pass"].iloc[0]
    assert outcome_check["status"] == "fail"
    assert "invalid deterministic execution artifact" in outcome_check["details"]
    assert str(tmp_path / "EURUSD_jforex_runtime_events.csv") == outcome_check["source_path"]


def test_build_stage14_artifacts_rejects_unreadable_local_runtime_events_file(
    tmp_path: Path,
) -> None:
    _write_stage14_green_inputs(tmp_path, "EURUSD")
    _write_runtime_events(tmp_path / "EURUSD_jforex_runtime_events.csv", "EURUSD")
    (tmp_path / "EURUSD_local_jforex_runtime_events.csv").write_bytes(b"\xff\xfe\x00\x81")
    _write_csv(
        tmp_path / "local_surrogate.csv",
        [{"symbol": "EURUSD", "local_jforex_surrogate_pass": True}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        reconcile_dir=tmp_path,
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    assert int(summary.loc[0, "missing_inputs"]) == 1
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"].iloc[0]
    assert surrogate_check["status"] == "fail"
    assert "invalid deterministic execution artifact" in surrogate_check["details"]
    assert str(tmp_path / "EURUSD_local_jforex_runtime_events.csv") == surrogate_check["source_path"]

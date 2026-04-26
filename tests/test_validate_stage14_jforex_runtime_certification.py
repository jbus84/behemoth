from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from scripts.run_jforex_dukascopy_matrix import _stage14_artifact_paths
import scripts.validate_stage14_jforex_runtime_certification as stage14_mod
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
        ("jforex_execution_lifecycle", "execution_lifecycle_pass"),
        ("jforex_ops", "operational_ready_pass"),
        ("outcome", "jforex_outcome_parity_pass"),
    ]:
        _write_csv(tmp_path / f"{symbol}_{name}.csv", [{"symbol": symbol, col: True}])


def _write_stage13_normalized_summary(
    tmp_path: Path,
    symbol: str,
    *,
    stage13_certification_outcome: str,
    stage13_go_decision: str,
    certification_outcome: str,
    go_decision: str,
) -> Path:
    path = tmp_path / "stage12_stage13_certification_summary.csv"
    _write_csv(
        path,
        [
            {
                "symbol": symbol,
                "stage12_certification_outcome": "PASS",
                "stage12_go_decision": "GO",
                "stage13_attempted": True,
                "stage13_certification_outcome": stage13_certification_outcome,
                "stage13_go_decision": stage13_go_decision,
                "certification_outcome": certification_outcome,
                "go_decision": go_decision,
            }
        ],
    )
    return path


def _write_stage14_bundle_inputs(
    bundle_dir: Path,
    symbol: str,
    *,
    stage13_certification_outcome: str = "PASS",
    stage13_go_decision: str = "GO",
    stage13_pass: bool = True,
    jforex_signal_pass: bool = True,
    jforex_execution_pass: bool = True,
    execution_lifecycle_pass: bool = True,
    operational_ready_pass: bool = True,
    outcome_pass: bool = True,
    local_surrogate_pass: bool | None = None,
    historical_deployable: bool | None = None,
    non_deployable_reason: str = "",
    verdict: str | None = None,
) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        bundle_dir / f"{symbol}_stage13.csv",
        [
            {
                "symbol": symbol,
                "stage13_dukascopy_testclient_pass": stage13_pass,
                "certification_outcome": stage13_certification_outcome,
                "go_decision": stage13_go_decision,
            }
        ],
    )
    _write_csv(
        bundle_dir / f"{symbol}_jforex_signal.csv",
        [{"symbol": symbol, "jforex_signal_parity_pass": jforex_signal_pass}],
    )
    _write_csv(
        bundle_dir / f"{symbol}_jforex_execution.csv",
        [{"symbol": symbol, "jforex_execution_parity_pass": jforex_execution_pass}],
    )
    _write_csv(
        bundle_dir / f"{symbol}_jforex_execution_lifecycle.csv",
        [{"symbol": symbol, "execution_lifecycle_pass": execution_lifecycle_pass}],
    )
    _write_csv(
        bundle_dir / f"{symbol}_jforex_ops.csv",
        [{"symbol": symbol, "operational_ready_pass": operational_ready_pass}],
    )
    _write_csv(
        bundle_dir / f"{symbol}_outcome.csv",
        [{"symbol": symbol, "jforex_outcome_parity_pass": outcome_pass}],
    )
    if local_surrogate_pass is not None or historical_deployable is not None or verdict is not None:
        row: dict[str, object] = {"symbol": symbol}
        if local_surrogate_pass is not None:
            row["local_jforex_surrogate_pass"] = local_surrogate_pass
        if historical_deployable is not None:
            row["historical_deployable"] = historical_deployable
        if non_deployable_reason:
            row["non_deployable_reason"] = non_deployable_reason
        if verdict is not None:
            row["verdict"] = verdict
        _write_csv(bundle_dir / f"{symbol}_local_jforex_surrogate.csv", [row])


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
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is True
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    assert int(summary.loc[0, "missing_inputs"]) == 6
    failed = checks[checks["status"] == "FAIL"]
    assert len(failed) == 6


def test_stage14_emits_process_pass_and_symbol_go_for_green_inputs(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle_202404"
    _write_stage14_bundle_inputs(
        bundle_dir,
        "EURUSD",
        local_surrogate_pass=True,
        historical_deployable=True,
        verdict="green",
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(bundle_dir / "*_stage13.csv"),
        jforex_signal_summary_glob=str(bundle_dir / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(bundle_dir / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(bundle_dir / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(bundle_dir / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(bundle_dir / "*_outcome.csv"),
        local_surrogate_summary_glob=str(bundle_dir / "*_local_jforex_surrogate.csv"),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
        target_bundle_dir=bundle_dir,
        target_model_month="202404",
        require_provenance=True,
    )

    assert summary.loc[0, "process_status"] == "PASS"
    assert summary.loc[0, "certification_outcome"] == "PASS"
    assert summary.loc[0, "go_decision"] == "GO"
    assert not checks["details"].str.contains("provenance", case=False).any()


def test_stage14_emits_process_pass_and_symbol_nogo_for_certified_non_deployable_symbol(
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "bundle_202404"
    _write_stage14_bundle_inputs(
        bundle_dir,
        "USDCAD",
        local_surrogate_pass=True,
        historical_deployable=False,
        non_deployable_reason="no_gate_states",
        verdict="NO_GO",
    )

    summary, checks = build_stage14_artifacts(
        symbols=["USDCAD"],
        stage13_summary_glob=str(bundle_dir / "*_stage13.csv"),
        jforex_signal_summary_glob=str(bundle_dir / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(bundle_dir / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(bundle_dir / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(bundle_dir / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(bundle_dir / "*_outcome.csv"),
        local_surrogate_summary_glob=str(bundle_dir / "*_local_jforex_surrogate.csv"),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
        target_bundle_dir=bundle_dir,
        target_model_month="202404",
        require_provenance=True,
    )

    assert summary.loc[0, "process_status"] == "PASS"
    assert summary.loc[0, "certification_outcome"] == "PASS"
    assert summary.loc[0, "go_decision"] == "NO_GO"
    assert summary.loc[0, "verdict"] == "NO_GO"
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"].iloc[0]
    assert "accepted non-deployable local surrogate no_go" in surrogate_check["details"].lower()


def test_stage14_emits_process_fail_when_inputs_are_mixed_from_wrong_bundle(
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "bundle_202404"
    wrong_bundle_dir = tmp_path / "other_bundle_202404"
    _write_stage14_bundle_inputs(bundle_dir, "EURUSD")
    _write_csv(
        wrong_bundle_dir / "EURUSD_jforex_execution.csv",
        [{"symbol": "EURUSD", "jforex_execution_parity_pass": True}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(bundle_dir / "*_stage13.csv"),
        jforex_signal_summary_glob=str(bundle_dir / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(wrong_bundle_dir / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(bundle_dir / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(bundle_dir / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(bundle_dir / "*_outcome.csv"),
        local_surrogate_summary_glob="",
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
        target_bundle_dir=bundle_dir,
        target_model_month="202404",
        require_provenance=True,
    )

    assert summary["process_status"].eq("FAIL").all()
    assert checks["details"].str.contains("provenance", case=False).any()
    execution_check = checks[checks["metric_name"] == "jforex_execution_parity_pass"].iloc[0]
    assert execution_check["status"] == "FAIL"
    assert execution_check["metric_value"] == 0


def test_stage14_accepts_month_scoped_recert_report_paths_with_bundle_inputs(
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2024-04"
    report_dir = tmp_path / "data/analysis/backtest_reconcile/2024-04/monthly_recert"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(
        report_dir / "stage12_stage13_certification_summary.csv",
        [
            {
                "symbol": "EURUSD",
                "stage12_certification_outcome": "PASS",
                "stage12_go_decision": "GO",
                "stage13_attempted": True,
                "stage13_certification_outcome": "PASS",
                "stage13_go_decision": "GO",
                "certification_outcome": "PASS",
                "go_decision": "GO",
            }
        ],
    )
    _write_csv(
        report_dir / "EURUSD_jforex_signal_parity_summary.csv",
        [{"symbol": "EURUSD", "jforex_signal_parity_pass": True}],
    )
    _write_csv(
        report_dir / "EURUSD_jforex_execution_parity_summary.csv",
        [{"symbol": "EURUSD", "jforex_execution_parity_pass": True}],
    )
    _write_csv(
        report_dir / "EURUSD_jforex_execution_lifecycle_summary.csv",
        [{"symbol": "EURUSD", "execution_lifecycle_pass": True}],
    )
    _write_csv(
        report_dir / "EURUSD_jforex_operational_ready_summary.csv",
        [{"symbol": "EURUSD", "operational_ready_pass": True}],
    )
    _write_csv(
        report_dir / "jforex_outcome_parity_summary.csv",
        [
            {
                "symbol": "EURUSD",
                "jforex_outcome_parity_pass": True,
                "overall_pass": True,
                "historical_deployable": True,
                "lock_dir": "configs/research/governance/oco_candidate_builds/2024-04",
            }
        ],
    )
    _write_csv(
        report_dir / "local_jforex_surrogate_summary.csv",
        [
            {
                "symbol": "EURUSD",
                "historical_deployable": True,
                "local_jforex_surrogate_pass": True,
                "verdict": "green",
            }
        ],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(report_dir / "stage12_stage13_certification_summary.csv"),
        jforex_signal_summary_glob=str(report_dir / "*_jforex_signal_parity_summary.csv"),
        jforex_execution_summary_glob=str(report_dir / "*_jforex_execution_parity_summary.csv"),
        jforex_lifecycle_summary_glob=str(report_dir / "*_jforex_execution_lifecycle_summary.csv"),
        jforex_operational_summary_glob=str(report_dir / "*_jforex_operational_ready_summary.csv"),
        jforex_outcome_summary_glob=str(report_dir / "jforex_outcome_parity_summary.csv"),
        local_surrogate_summary_glob=str(report_dir / "local_jforex_surrogate_summary.csv"),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
        target_bundle_dir=bundle_dir,
        target_model_month="2024-04",
        require_provenance=True,
    )

    assert summary.loc[0, "process_status"] == "PASS"
    assert summary.loc[0, "certification_outcome"] == "PASS"
    assert summary.loc[0, "go_decision"] == "GO"
    assert not checks["details"].astype(str).str.contains("provenance mismatch", case=False).any()


def test_stage14_emits_process_fail_when_glob_matches_target_and_non_target_bundle(
    tmp_path: Path,
) -> None:
    bundle_dir = tmp_path / "bundle_202404"
    wrong_bundle_dir = tmp_path / "shadow_bundle_202404"
    _write_stage14_bundle_inputs(bundle_dir, "EURUSD")
    _write_csv(
        wrong_bundle_dir / "EURUSD_jforex_execution.csv",
        [{"symbol": "EURUSD", "jforex_execution_parity_pass": True}],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(bundle_dir / "*_stage13.csv"),
        jforex_signal_summary_glob=str(bundle_dir / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=",".join(
            [
                str(bundle_dir / "*_jforex_execution.csv"),
                str(wrong_bundle_dir / "*_jforex_execution.csv"),
            ]
        ),
        jforex_lifecycle_summary_glob=str(bundle_dir / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(bundle_dir / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(bundle_dir / "*_outcome.csv"),
        local_surrogate_summary_glob="",
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
        target_bundle_dir=bundle_dir,
        target_model_month="2024-04",
        require_provenance=True,
    )

    assert summary["process_status"].eq("FAIL").all()
    execution_check = checks[checks["metric_name"] == "jforex_execution_parity_pass"].iloc[0]
    assert execution_check["status"] == "FAIL"
    assert "provenance mismatch" in execution_check["details"].lower()


def test_stage14_rejects_fail_go_combination(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle_202404"
    _write_stage14_bundle_inputs(
        bundle_dir,
        "EURUSD",
        stage13_pass=False,
        stage13_certification_outcome="FAIL",
        stage13_go_decision="GO",
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(bundle_dir / "*_stage13.csv"),
        jforex_signal_summary_glob=str(bundle_dir / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(bundle_dir / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(bundle_dir / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(bundle_dir / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(bundle_dir / "*_outcome.csv"),
        local_surrogate_summary_glob="",
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
        target_bundle_dir=bundle_dir,
        target_model_month="202404",
        require_provenance=True,
    )

    assert summary["process_status"].eq("FAIL").all()
    assert summary.loc[0, "go_decision"] == "NO_GO"
    assert checks["details"].str.contains("forbidden fail/go combination", case=False).any()
    stage13_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"].iloc[0]
    assert stage13_check["status"] == "FAIL"
    assert stage13_check["metric_value"] == 0


def test_stage14_rejects_fail_go_from_any_matched_stage13_row(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle_202404"
    shadow_dir = tmp_path / "shadow_bundle_202404"
    _write_stage14_bundle_inputs(bundle_dir, "EURUSD")
    _write_csv(
        shadow_dir / "EURUSD_stage13.csv",
        [
            {
                "symbol": "EURUSD",
                "stage13_dukascopy_testclient_pass": False,
                "certification_outcome": "FAIL",
                "go_decision": "GO",
            }
        ],
    )

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=",".join(
            [str(bundle_dir / "*_stage13.csv"), str(shadow_dir / "*_stage13.csv")]
        ),
        jforex_signal_summary_glob=str(bundle_dir / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(bundle_dir / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(bundle_dir / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(bundle_dir / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(bundle_dir / "*_outcome.csv"),
        local_surrogate_summary_glob="",
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
        target_bundle_dir=bundle_dir,
        target_model_month="2024-04",
        require_provenance=True,
    )

    assert summary["process_status"].eq("FAIL").all()
    stage13_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"].iloc[0]
    assert stage13_check["status"] == "FAIL"
    assert "forbidden fail/go combination" in stage13_check["details"].lower()
    assert "shadow_bundle_202404" in stage13_check["source_path"]


def test_build_stage14_artifacts_ignores_local_surrogate_matches(tmp_path: Path) -> None:
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
        tmp_path / "GBPUSD_jforex_execution_lifecycle.csv",
        [{"symbol": "GBPUSD", "execution_lifecycle_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_local_jforex_execution_lifecycle.csv",
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*jforex_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
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


def test_build_stage14_artifacts_uses_normalized_stage13_summary(tmp_path: Path) -> None:
    stage13_summary = _write_stage13_normalized_summary(
        tmp_path,
        "GBPUSD",
        stage13_certification_outcome="PASS",
        stage13_go_decision="NO_GO",
        certification_outcome="PASS",
        go_decision="NO_GO",
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
        tmp_path / "GBPUSD_jforex_execution_lifecycle.csv",
        [{"symbol": "GBPUSD", "execution_lifecycle_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_jforex_ops.csv",
        [{"symbol": "GBPUSD", "operational_ready_pass": True}],
    )
    _write_csv(
        tmp_path / "GBPUSD_outcome.csv",
        [{"symbol": "GBPUSD", "jforex_outcome_parity_pass": True}],
    )
    local_surrogate_path = _write_local_surrogate_row(
        tmp_path,
        "GBPUSD",
        historical_deployable=False,
        non_deployable_reason="no_gate_states",
        verdict="NO_GO",
    )

    summary, checks = build_stage14_artifacts(
        symbols=["GBPUSD"],
        stage13_summary_glob=str(stage13_summary),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(local_surrogate_path),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    stage13_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"].iloc[0]
    assert stage13_check["status"] == "PASS"
    assert summary.loc[0, "stage13_certification_outcome"] == "PASS"
    assert summary.loc[0, "stage13_go_decision"] == "NO_GO"
    assert summary.loc[0, "certification_outcome"] == "PASS"
    assert summary.loc[0, "go_decision"] == "NO_GO"
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is True
    assert bool(summary.loc[0, "local_jforex_surrogate_pass"]) is True
    assert summary.loc[0, "verdict"] == "NO_GO"


def test_build_stage14_artifacts_keeps_requested_symbol_scope(tmp_path: Path) -> None:
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
        tmp_path / "GBPUSD_jforex_execution_lifecycle.csv",
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
        tmp_path / "EURUSD_jforex_execution_lifecycle.csv",
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
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
        tmp_path / "EURUSD_jforex_execution_lifecycle.csv",
        [{"symbol": "EURUSD", "execution_lifecycle_pass": True}]
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
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
    assert outcome_check.iloc[0]["status"] == "FAIL"


def test_build_stage14_artifacts_includes_local_surrogate_check(tmp_path: Path) -> None:
    """Stage 14 must include local_jforex_surrogate_pass as a prerequisite check."""
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
        tmp_path / "EURUSD_jforex_execution_lifecycle.csv",
        [{"symbol": "EURUSD", "execution_lifecycle_pass": True}]
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob="",
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"]
    assert len(surrogate_check) == 1
    assert surrogate_check.iloc[0]["status"] == "FAIL"


def test_build_stage14_artifacts_accepts_local_surrogate_nogo_for_non_deployable_symbol(
    tmp_path: Path,
) -> None:
    _write_csv(
        tmp_path / "USDCAD_stage13.csv",
        [
            {
                "symbol": "USDCAD",
                "stage13_dukascopy_testclient_pass": True,
                "certification_outcome": "PASS",
                "go_decision": "NO_GO",
            }
        ],
    )
    for name, col in [
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("jforex_execution_lifecycle", "execution_lifecycle_pass"),
        ("jforex_ops", "operational_ready_pass"),
        ("outcome", "jforex_outcome_parity_pass"),
    ]:
        _write_csv(tmp_path / f"USDCAD_{name}.csv", [{"symbol": "USDCAD", col: True}])
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(local_surrogate_path),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"]
    assert len(surrogate_check) == 1
    assert surrogate_check.iloc[0]["status"] == "PASS"
    assert "no_go" in surrogate_check.iloc[0]["details"].lower()
    assert bool(surrogate_check.iloc[0]["metric_value"]) is True
    stage13_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"].iloc[0]
    assert stage13_check["status"] == "PASS"
    assert "PASS / NO_GO" in stage13_check["details"]
    assert summary.loc[0, "stage13_certification_outcome"] == "PASS"
    assert summary.loc[0, "stage13_go_decision"] == "NO_GO"
    assert summary.loc[0, "certification_outcome"] == "PASS"
    assert summary.loc[0, "go_decision"] == "NO_GO"
    assert bool(summary.loc[0, "local_jforex_surrogate_pass"]) is True
    assert summary.loc[0, "verdict"] == "NO_GO"
    report_text = (tmp_path / "out" / "report.md").read_text()
    snapshot_text = (tmp_path / "out" / "snapshot.md").read_text()
    assert "PASS / NO_GO is accepted as a valid prerequisite" in report_text
    assert "PASS / NO_GO" in snapshot_text
    assert "accepted as a valid prerequisite" in snapshot_text


def test_stage14_makefile_default_points_to_normalized_stage13_summary() -> None:
    makefile = Path(__file__).resolve().parents[1] / "Makefile"
    stage14_block = makefile.read_text().split("stage14-jforex-cert:", 1)[1]
    assert "stage12_stage13_certification_summary.csv" in stage14_block
    assert "stage13_dukascopy_testclient_summary.csv" not in stage14_block


def test_stage14_main_forwards_provenance_flags(monkeypatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}

    def fake_build_stage14_artifacts(**kwargs: object) -> tuple[pd.DataFrame, pd.DataFrame]:
        recorded.update(kwargs)
        return pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr(stage14_mod, "build_stage14_artifacts", fake_build_stage14_artifacts)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_stage14_jforex_runtime_certification.py",
            "--target-bundle-dir",
            str(tmp_path / "bundle_202404"),
            "--target-model-month",
            "202404",
            "--require-provenance",
        ],
    )

    stage14_mod.main()

    assert recorded["target_bundle_dir"] == tmp_path / "bundle_202404"
    assert recorded["target_model_month"] == "202404"
    assert recorded["require_provenance"] is True


def test_stage14_main_rejects_incomplete_provenance_args(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_stage14_jforex_runtime_certification.py",
            "--target-bundle-dir",
            str(tmp_path / "bundle_202404"),
            "--require-provenance",
        ],
    )

    with pytest.raises(SystemExit):
        stage14_mod.main()


def test_build_stage14_artifacts_marks_non_deployable_symbol_as_nogo(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "USDCAD_stage13.csv",
        [
            {
                "symbol": "USDCAD",
                "stage13_dukascopy_testclient_pass": True,
                "certification_outcome": "PASS",
                "go_decision": "NO_GO",
            }
        ],
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
        tmp_path / "USDCAD_jforex_execution_lifecycle.csv",
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(local_surrogate_path),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    for metric_name in (
        "jforex_signal_parity_pass",
        "jforex_execution_parity_pass",
        "jforex_outcome_parity_pass",
    ):
        check = checks[checks["metric_name"] == metric_name]
        assert len(check) == 1
        assert check.iloc[0]["status"] == "NO_GO"
        assert "historical non-deployable" in str(check.iloc[0]["details"]).lower()
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"]
    assert len(surrogate_check) == 1
    assert surrogate_check.iloc[0]["status"] == "PASS"
    assert bool(summary.loc[0, "local_jforex_surrogate_pass"]) is True
    stage13_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"].iloc[0]
    assert stage13_check["status"] == "PASS"
    assert "PASS / NO_GO" in stage13_check["details"]
    assert summary.loc[0, "stage13_certification_outcome"] == "PASS"
    assert summary.loc[0, "stage13_go_decision"] == "NO_GO"
    assert summary.loc[0, "certification_outcome"] == "FAIL"
    assert summary.loc[0, "go_decision"] == "NO_GO"
    assert summary.loc[0, "verdict"] == "red"


def test_build_stage14_artifacts_rejects_contradictory_stage13_inputs(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "EURUSD_stage13.csv",
        [
            {
                "symbol": "EURUSD",
                "stage13_dukascopy_testclient_pass": False,
                "certification_outcome": "PASS",
                "go_decision": "GO",
            }
        ],
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
        tmp_path / "EURUSD_jforex_execution_lifecycle.csv",
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    stage13_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"].iloc[0]
    assert stage13_check["status"] == "FAIL"
    assert "contradictory Stage 13 inputs" in stage13_check["details"]
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    assert summary.loc[0, "certification_outcome"] == "FAIL"
    assert summary.loc[0, "go_decision"] == "NO_GO"


def test_build_stage14_artifacts_rejects_deployable_symbol_with_local_surrogate_nogo(
    tmp_path: Path,
) -> None:
    _write_stage14_green_inputs(tmp_path, "EURUSD")
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(local_surrogate_path),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"]
    assert len(surrogate_check) == 1
    assert surrogate_check.iloc[0]["status"] == "FAIL"
    assert "historical_deployable" in surrogate_check.iloc[0]["details"].lower()
    assert bool(summary.loc[0, "local_jforex_surrogate_pass"]) is False
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False


def test_build_stage14_artifacts_green_with_all_seven_checks(tmp_path: Path) -> None:
    """Stage 14 is green only when all 7 checks pass."""
    for name, col in [
        ("stage13", "stage13_dukascopy_testclient_pass"),
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("jforex_execution_lifecycle", "execution_lifecycle_pass"),
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    assert "execution_lifecycle_pass" in summary.columns
    assert "oco_lifecycle_pass" not in summary.columns
    lifecycle_check = checks[checks["metric_name"] == "execution_lifecycle_pass"]
    assert len(lifecycle_check) == 1
    assert lifecycle_check.iloc[0]["status"] == "PASS"
    assert "oco_lifecycle_pass" not in set(checks["metric_name"])
    report_text = (tmp_path / "out" / "report.md").read_text()
    snapshot_text = (tmp_path / "out" / "snapshot.md").read_text()
    assert "execution_lifecycle_pass" in report_text
    assert "execution lifecycle correctness" in snapshot_text
    assert "local JForex surrogate readiness" in snapshot_text
    assert summary.loc[0, "verdict"] == "green"
    assert int(summary.loc[0, "missing_inputs"]) == 0
    assert len(checks) == 7
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is True


def test_build_stage14_artifacts_fails_when_input_artifact_is_stale(tmp_path: Path) -> None:
    """A Stage 14 input CSV with evaluated_at_utc older than max_artifact_age_days must fail."""
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
        ("jforex_execution_lifecycle", "execution_lifecycle_pass"),
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
        max_artifact_age_days=7,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    stage13_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"]
    assert stage13_check.iloc[0]["status"] == "FAIL"
    assert "stale" in stage13_check.iloc[0]["details"].lower()


def test_build_stage14_artifacts_passes_when_all_fresh(tmp_path: Path) -> None:
    """Staleness check must not fire when all inputs are recent."""
    fresh_ts = _utc_str()
    for name, col in [
        ("stage13", "stage13_dukascopy_testclient_pass"),
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("jforex_execution_lifecycle", "execution_lifecycle_pass"),
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob="",
        local_surrogate_summary_glob="",
        max_artifact_age_days=7,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )
    # outcome+surrogate both missing → cert fails overall, but stage13 check must be "pass" (fresh)
    stage13_check = checks[checks["metric_name"] == "stage13_dukascopy_testclient_pass"]
    assert stage13_check.iloc[0]["status"] == "PASS"
    assert stage13_check.iloc[0]["details"] == ""


def test_build_stage14_artifacts_accepts_non_deployable_local_surrogate_nogo(
    tmp_path: Path,
) -> None:
    for name, col in [
        ("stage13", "stage13_dukascopy_testclient_pass"),
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("jforex_execution_lifecycle", "execution_lifecycle_pass"),
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"].iloc[0]
    assert surrogate_check["status"] == "PASS"
    assert "non-deployable" in surrogate_check["details"].lower()
    assert "historical_deployable=false" in surrogate_check["details"].lower()
    assert "no_gate_states" in surrogate_check["details"]
    assert bool(summary.loc[0, "local_jforex_surrogate_pass"]) is True
    assert summary.loc[0, "verdict"] == "NO_GO"


def test_build_stage14_artifacts_rejects_deployable_local_surrogate_nogo(tmp_path: Path) -> None:
    for name, col in [
        ("stage13", "stage13_dukascopy_testclient_pass"),
        ("jforex_signal", "jforex_signal_parity_pass"),
        ("jforex_execution", "jforex_execution_parity_pass"),
        ("jforex_execution_lifecycle", "execution_lifecycle_pass"),
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "local_jforex_surrogate_pass"]) is False
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    surrogate_check = checks[checks["metric_name"] == "local_jforex_surrogate_pass"].iloc[0]
    assert surrogate_check["status"] == "FAIL"
    assert "historical_deployable" in surrogate_check["details"].lower()


def test_build_stage14_artifacts_rejects_legacy_oco_lifecycle_only_inputs(tmp_path: Path) -> None:
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
        [{"symbol": "EURUSD", "oco_lifecycle_pass": True}],
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
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    lifecycle_check = checks[checks["source_path"].astype(str).str.endswith("EURUSD_jforex_lifecycle.csv")]
    assert len(lifecycle_check) == 1
    assert lifecycle_check.iloc[0]["source_path"].endswith("EURUSD_jforex_lifecycle.csv")
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    assert int(summary.loc[0, "missing_inputs"]) >= 1
    execution_lifecycle_checks = checks[checks["metric_name"] == "execution_lifecycle_pass"]
    assert len(execution_lifecycle_checks) == 1
    assert execution_lifecycle_checks.iloc[0]["status"] == "FAIL"


def test_build_stage14_artifacts_rejects_lifecycle_pass_only_inputs(tmp_path: Path) -> None:
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
        tmp_path / "EURUSD_jforex_execution_lifecycle.csv",
        [{"symbol": "EURUSD", "lifecycle_pass": True}],
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
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_execution_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        jforex_outcome_summary_glob=str(tmp_path / "*_outcome.csv"),
        local_surrogate_summary_glob=str(tmp_path / "local_surrogate.csv"),
        max_artifact_age_days=0,
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    lifecycle_check = checks[checks["metric_name"] == "execution_lifecycle_pass"]
    assert len(lifecycle_check) == 1
    assert lifecycle_check.iloc[0]["status"] == "FAIL"
    assert lifecycle_check.iloc[0]["source_path"].endswith("EURUSD_jforex_execution_lifecycle.csv")
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    assert int(summary.loc[0, "missing_inputs"]) >= 1


def test_stage14_matrix_helper_uses_execution_lifecycle_artifact_name() -> None:
    paths = _stage14_artifact_paths(Path("/tmp/report"), "EURUSD")
    assert Path("/tmp/report/EURUSD_jforex_execution_lifecycle_summary.csv") in paths
    assert all("oco_lifecycle_summary" not in str(path) for path in paths)

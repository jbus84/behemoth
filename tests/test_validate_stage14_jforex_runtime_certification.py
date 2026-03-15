from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.validate_stage14_jforex_runtime_certification import build_stage14_artifacts


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def test_build_stage14_artifacts_marks_green_when_all_checks_pass(tmp_path: Path) -> None:
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

    summary, checks = build_stage14_artifacts(
        symbols=["EURUSD"],
        stage13_summary_glob=str(tmp_path / "*_stage13.csv"),
        jforex_signal_summary_glob=str(tmp_path / "*_jforex_signal.csv"),
        jforex_execution_summary_glob=str(tmp_path / "*_jforex_execution.csv"),
        jforex_lifecycle_summary_glob=str(tmp_path / "*_jforex_lifecycle.csv"),
        jforex_operational_summary_glob=str(tmp_path / "*_jforex_ops.csv"),
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is True
    assert summary.loc[0, "verdict"] == "green"
    assert int(summary.loc[0, "missing_inputs"]) == 0
    assert len(checks) == 5


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
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is True
    assert bool(summary.loc[0, "stage14_jforex_cert_pass"]) is False
    assert int(summary.loc[0, "missing_inputs"]) == 4
    failed = checks[checks["status"] == "fail"]
    assert len(failed) == 4

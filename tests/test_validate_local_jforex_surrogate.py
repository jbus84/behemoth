from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


def test_stage12_bridge_reads_from_stage13_summary(tmp_path: Path) -> None:
    from scripts.validate_local_jforex_surrogate import build_artifacts

    # Write a minimal stage13 summary CSV (single multi-symbol file)
    stage13 = tmp_path / "stage13_dukascopy_testclient_summary.csv"
    with open(stage13, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "stage12_api_parity_pass", "verdict"])
        w.writeheader()
        w.writerow({"symbol": "EURUSD", "stage12_api_parity_pass": "True", "verdict": "green"})

    summary, checks = build_artifacts(
        symbols=["EURUSD"],
        stage12_summary_glob=str(stage13),
        local_signal_summary_glob="",
        local_execution_summary_glob="",
        local_lifecycle_summary_glob="",
        local_operational_summary_glob="",
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        report_out=tmp_path / "report.md",
    )
    stage12_row = checks[checks["check_id"] == "STAGE12_API_PARITY_PASS"]
    assert len(stage12_row) > 0, "STAGE12_API_PARITY_PASS check not found in checks output"
    assert stage12_row["status"].iloc[0] == "pass"


def test_build_artifacts_includes_outcome_parity(tmp_path):
    from scripts.validate_local_jforex_surrogate import build_artifacts

    outcome_csv = tmp_path / "EURUSD_local_jforex_outcome_parity_summary.csv"
    with open(outcome_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "overall_pass", "jforex_outcome_parity_pass"])
        w.writeheader()
        w.writerow({"symbol": "EURUSD", "overall_pass": "True", "jforex_outcome_parity_pass": "True"})

    summary, checks = build_artifacts(
        symbols=["EURUSD"],
        stage12_summary_glob="",
        local_signal_summary_glob="",
        local_execution_summary_glob="",
        local_lifecycle_summary_glob="",
        local_operational_summary_glob="",
        local_outcome_summary_glob=str(tmp_path / "*_local_jforex_outcome_parity_summary.csv"),
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        report_out=tmp_path / "report.md",
    )
    outcome_row = checks[checks["check_id"] == "JFOREX_OUTCOME_PARITY_PASS"]
    assert len(outcome_row) == 1, "JFOREX_OUTCOME_PARITY_PASS check not found"
    assert outcome_row["status"].iloc[0] == "pass"

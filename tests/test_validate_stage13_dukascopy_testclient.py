from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.validate_stage13_dukascopy_testclient import build_stage13_artifacts


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def test_build_stage13_artifacts_marks_green_when_all_checks_pass(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "EURUSD_stage12.csv",
        [{"symbol": "EURUSD", "stage12_api_parity_pass": True}],
    )
    _write_csv(
        tmp_path / "EURUSD_dukascopy_testclient.csv",
        [{"symbol": "EURUSD", "selected_parity_pass": True, "overall_pass": True}],
    )

    summary, checks = build_stage13_artifacts(
        symbols=["EURUSD"],
        stage12_summary_glob=str(tmp_path / "*_stage12.csv"),
        dukascopy_testclient_summary_glob=str(tmp_path / "*_dukascopy_testclient.csv"),
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is True
    assert summary.loc[0, "verdict"] == "green"
    assert int(summary.loc[0, "missing_inputs"]) == 0
    assert len(checks) == 3


def test_build_stage13_artifacts_fails_when_replay_inputs_missing(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "GBPUSD_stage12.csv",
        [{"symbol": "GBPUSD", "stage12_api_parity_pass": True}],
    )

    summary, checks = build_stage13_artifacts(
        symbols=["GBPUSD"],
        stage12_summary_glob=str(tmp_path / "*_stage12.csv"),
        dukascopy_testclient_summary_glob="",
        out_summary_csv=tmp_path / "out" / "summary.csv",
        out_checks_csv=tmp_path / "out" / "checks.csv",
        report_out=tmp_path / "out" / "report.md",
        snapshot_out=tmp_path / "out" / "snapshot.md",
    )

    assert bool(summary.loc[0, "stage12_api_parity_pass"]) is True
    assert bool(summary.loc[0, "stage13_dukascopy_testclient_pass"]) is False
    assert int(summary.loc[0, "missing_inputs"]) == 2
    failed = checks[checks["status"] == "fail"]
    assert len(failed) == 2

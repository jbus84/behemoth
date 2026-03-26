from __future__ import annotations

import json
import sys

import pytest

import scripts.run_promote_live as run_promote_live


def test_main_archives_candidate_build_bundle(monkeypatch, tmp_path) -> None:
    verify_calls: list[str] = []
    build_bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-02"
    build_bundle_dir.mkdir(parents=True)
    source_predictions = (
        build_bundle_dir
        / "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2026_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet"
    )
    source_states = (
        build_bundle_dir
        / "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling/EURUSD_oco_reduced_state_schedule.csv"
    )
    source_predictions.parent.mkdir(parents=True)
    source_states.parent.mkdir(parents=True)
    source_predictions.write_text("predictions\n")
    source_states.write_text("states\n")
    lock_path = build_bundle_dir / "eurusd_oco_live_lock.json"
    lock_path.write_text(
        json.dumps(
            {
                "artifacts": {
                    "predictions_path": str(source_predictions),
                    "reduced_states_csv_path": str(source_states),
                    "reduced_summary_path": "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling/EURUSD_oco_reduced_summary.csv",
                },
                "symbol": "EURUSD",
            },
            indent=2,
        )
        + "\n"
    )
    archive_dir = tmp_path / "configs/research/governance/oco_history_dukascopy_candidate"
    archive_dir.mkdir(parents=True)
    (archive_dir / "stale.txt").write_text("stale\n")

    monkeypatch.setattr(run_promote_live, "_verify_cert", lambda report_dir: verify_calls.append(report_dir))
    monkeypatch.setattr(run_promote_live, "_last_complete_month", lambda override=None: "2026-02")
    monkeypatch.setattr(run_promote_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_promote_live.py", "--report-dir", "data/analysis/backtest_reconcile"])

    run_promote_live.main()

    assert verify_calls == ["data/analysis/backtest_reconcile"]
    promoted_lock = archive_dir / "2026-02" / "eurusd_oco_live_lock.json"
    promoted_data = json.loads(promoted_lock.read_text())
    assert promoted_data["artifacts"]["predictions_path"] == str(
        archive_dir
        / "2026-02"
        / "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2026_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet"
    )
    assert promoted_data["artifacts"]["reduced_states_csv_path"] == str(
        archive_dir
        / "2026-02"
        / "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling/EURUSD_oco_reduced_state_schedule.csv"
    )
    assert promoted_data["artifacts"]["reduced_summary_path"] == "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling/EURUSD_oco_reduced_summary.csv"


def test_main_requires_existing_build_bundle(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_promote_live, "_verify_cert", lambda report_dir: None)
    monkeypatch.setattr(run_promote_live, "_last_complete_month", lambda override=None: "2026-02")
    monkeypatch.setattr(run_promote_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_promote_live.py", "--report-dir", "data/analysis/backtest_reconcile"])

    with pytest.raises(
        SystemExit,
        match=r"run make monthly-build and make monthly-recert first",
    ):
        run_promote_live.main()

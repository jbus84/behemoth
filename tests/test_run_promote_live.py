from __future__ import annotations

import csv
import json
import sys
from datetime import date

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
    source_model_cbm = build_bundle_dir / "models/oco/EURUSD_model_2026-02.cbm"
    source_threshold_json = build_bundle_dir / "models/oco/EURUSD_model_2026-02.json"
    source_model_cbm.parent.mkdir(parents=True, exist_ok=True)
    source_model_cbm.write_text("cbm\n")
    source_threshold_json.write_text('{"threshold": 1.23}\n')
    lock_path = build_bundle_dir / "eurusd_oco_live_lock.json"
    lock_path.write_text(
        json.dumps(
            {
                "artifacts": {
                    "model_cbm_path": str(source_model_cbm),
                    "model_threshold_json_path": str(source_threshold_json),
                    "predictions_path": str(source_predictions),
                    "reduced_states_csv_path": str(source_states),
                    "reduced_summary_path": "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling/EURUSD_oco_reduced_summary.csv",
                    "live_deployable": True,
                },
                "state_universe": {"count": 7},
                "locked_runtime": {"production_cap_pips": 1.2},
                "symbol": "EURUSD",
            },
            indent=2,
        )
        + "\n"
    )
    archive_dir = tmp_path / "configs/research/governance/oco_history_dukascopy_candidate"
    archive_dir.mkdir(parents=True)
    (archive_dir / "stale.txt").write_text("stale\n")

    monkeypatch.setattr(
        run_promote_live,
        "_verify_cert",
        lambda report_dir, model_month: verify_calls.append(f"{report_dir}:{model_month}"),
    )
    monkeypatch.setattr(run_promote_live, "_last_complete_month", lambda override=None: "2026-02")
    monkeypatch.setattr(run_promote_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["run_promote_live.py", "--report-dir", "data/analysis/backtest_reconcile"]
    )

    run_promote_live.main()

    assert verify_calls == ["data/analysis/backtest_reconcile:2026-02"]
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
    assert (
        promoted_data["artifacts"]["reduced_summary_path"]
        == "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling/EURUSD_oco_reduced_summary.csv"
    )

    index_path = archive_dir / "index.csv"
    assert index_path.exists()
    rows = list(csv.DictReader(index_path.open()))
    assert rows == [
        {
            "symbol": "EURUSD",
            "month": "2026-02",
            "lock_path": str(promoted_lock),
            "allowed_states_path": str(
                archive_dir
                / "2026-02"
                / "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling/EURUSD_oco_reduced_state_schedule.csv"
            ),
            "model_cbm_path": str(archive_dir / "2026-02" / "models/oco/EURUSD_model_2026-02.cbm"),
            "threshold_json_path": str(
                archive_dir / "2026-02" / "models/oco/EURUSD_model_2026-02.json"
            ),
            "candidates_count": "7",
            "production_cap_pips": "1.2",
            "live_deployable": "True",
        }
    ]


def test_main_requires_existing_build_bundle(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_promote_live, "_verify_cert", lambda report_dir, model_month: None)
    monkeypatch.setattr(run_promote_live, "_last_complete_month", lambda override=None: "2026-02")
    monkeypatch.setattr(run_promote_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["run_promote_live.py", "--report-dir", "data/analysis/backtest_reconcile"]
    )

    with pytest.raises(
        SystemExit,
        match=r"run make monthly-build and make monthly-recert first",
    ):
        run_promote_live.main()


def test_verify_cert_requires_matching_month_status(tmp_path) -> None:
    report_dir = tmp_path / "data/analysis/backtest_reconcile"
    report_dir.mkdir(parents=True)
    (report_dir / run_promote_live.CERT_CHECKS_FILENAME).write_text(
        "symbol,check_id,status,severity,evaluated_at_utc\n"
        f"EURUSD,C1,pass,critical,{date.today().isoformat()}T12:00:00Z\n"
    )
    status_path = report_dir / run_promote_live.MONTHLY_RECERT_STATUS_FILENAME
    status_path.write_text(
        json.dumps(
            {
                "model_month": "2026-03",
                "evaluated_at_utc": f"{date.today().isoformat()}T12:00:00Z",
                "overall_pass": True,
            }
        )
        + "\n"
    )

    with pytest.raises(SystemExit, match=r"cert status month mismatch"):
        run_promote_live._verify_cert(
            "data/analysis/backtest_reconcile", "2026-02", repo_root=tmp_path
        )

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import date

import pytest

import scripts.run_promote_live as run_promote_live


def _make_valid_provenance_status(model_month: str) -> dict:
    """Create a valid monthly recert status dict for testing."""
    return {
        "dag_node_id": "monthly_recert",
        "model_month": model_month,
        "process_verdict": "PASS",
        "target_branch": "main",
        "target_commit": "abc1234567890000000000000000000000000001",
        "git_dirty": False,
        "symbol_decisions": {"EURUSD": "GO"},
        "lock_fingerprint": "fp-abc",
    }


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
    monkeypatch.setattr(run_promote_live, "_load_go_symbols", lambda report_dir, model_month: ["EURUSD"])
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


def test_promote_live_requires_process_status_pass(tmp_path) -> None:
    report_dir = tmp_path / "data/analysis/backtest_reconcile"
    report_dir.mkdir(parents=True)
    today = f"{date.today().isoformat()}T12:00:00Z"
    (report_dir / run_promote_live.CERT_CHECKS_FILENAME).write_text(
        f"symbol,check_id,status,severity,evaluated_at_utc\nEURUSD,C1,pass,critical,{today}\n"
    )
    (report_dir / run_promote_live.MONTHLY_RECERT_STATUS_FILENAME).write_text(
        json.dumps(
            {
                "model_month": "2026-02",
                "evaluated_at_utc": today,
                "overall_pass": True,
            }
        )
        + "\n"
    )
    (report_dir / run_promote_live.CERT_SUMMARY_FILENAME).write_text(
        "symbol,process_status,go_decision\nEURUSD,FAIL,NO_GO\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match=r"process_status.*PASS"):
        run_promote_live._load_go_symbols(
            "data/analysis/backtest_reconcile", "2026-02", repo_root=tmp_path
        )


def test_promote_live_archives_full_bundle_but_updates_active_live_governance_only_for_go_symbols(
    monkeypatch, tmp_path
) -> None:
    build_bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-02"
    build_bundle_dir.mkdir(parents=True)
    archive_dir = tmp_path / "configs/research/governance/oco_history_dukascopy_candidate"
    active_dir = tmp_path / "configs/research/governance/oco"
    archive_dir.mkdir(parents=True)
    active_dir.mkdir(parents=True)
    (active_dir / "audusd_oco_live_lock.json").write_text("stale\n", encoding="utf-8")

    for symbol in ("EURUSD", "AUDUSD"):
        lower = symbol.lower()
        model_dir = build_bundle_dir / "models/oco"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_cbm = model_dir / f"{symbol}_model_2026-02.cbm"
        model_thr = model_dir / f"{symbol}_model_2026-02.json"
        model_cbm.write_text("cbm\n", encoding="utf-8")
        model_thr.write_text('{"threshold": 1.23}\n', encoding="utf-8")
        allowed_states = build_bundle_dir / f"{lower}_oco_allowed_states.csv"
        allowed_states.write_text("symbol,state_id\n", encoding="utf-8")
        (build_bundle_dir / f"{lower}_oco_live_lock.json").write_text(
            json.dumps(
                {
                    "symbol": symbol,
                    "artifacts": {
                        "model_cbm_path": str(model_cbm),
                        "model_threshold_json_path": str(model_thr),
                        "reduced_states_csv_path": str(allowed_states),
                        "live_deployable": symbol == "EURUSD",
                    },
                    "state_universe": {"count": 1 if symbol == "EURUSD" else 0},
                    "locked_runtime": {"production_cap_pips": 1.2},
                }
            )
            + "\n",
            encoding="utf-8",
        )

    report_dir = tmp_path / "data/analysis/backtest_reconcile"
    report_dir.mkdir(parents=True)
    today = f"{date.today().isoformat()}T12:00:00Z"
    (report_dir / run_promote_live.CERT_CHECKS_FILENAME).write_text(
        "\n".join(
            [
                "symbol,check_id,status,severity,evaluated_at_utc",
                f"EURUSD,C1,pass,critical,{today}",
                f"AUDUSD,C1,nogo,critical,{today}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (report_dir / run_promote_live.MONTHLY_RECERT_STATUS_FILENAME).write_text(
        json.dumps(
            {
                "dag_node_id": "monthly_recert",
                "model_month": "2026-02",
                "evaluated_at_utc": today,
                "overall_pass": True,
                "process_verdict": "PASS",
                "target_branch": "main",
                "target_commit": "abc123",
                "git_dirty": False,
                "symbol_decisions": {"EURUSD": "GO", "AUDUSD": "NO_GO"},
                "lock_fingerprint": "fp-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (report_dir / run_promote_live.CERT_SUMMARY_FILENAME).write_text(
        "\n".join(
            [
                "symbol,process_status,go_decision",
                "EURUSD,PASS,GO",
                "AUDUSD,PASS,NO_GO",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(run_promote_live, "_last_complete_month", lambda override=None: "2026-02")
    monkeypatch.setattr(run_promote_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["run_promote_live.py", "--report-dir", "data/analysis/backtest_reconcile"]
    )

    run_promote_live.main()

    assert (archive_dir / "2026-02" / "eurusd_oco_live_lock.json").exists()
    assert (archive_dir / "2026-02" / "audusd_oco_live_lock.json").exists()
    assert (active_dir / "eurusd_oco_live_lock.json").exists()
    assert not (active_dir / "audusd_oco_live_lock.json").exists()


def test_verify_cert_requires_dag_provenance_fields(tmp_path) -> None:
    report_dir = tmp_path / "data/analysis/backtest_reconcile"
    report_dir.mkdir(parents=True)
    today = f"{date.today().isoformat()}T12:00:00Z"
    (report_dir / run_promote_live.CERT_CHECKS_FILENAME).write_text(
        f"symbol,check_id,status,severity,evaluated_at_utc\nEURUSD,C1,pass,critical,{today}\n",
        encoding="utf-8",
    )
    (report_dir / run_promote_live.MONTHLY_RECERT_STATUS_FILENAME).write_text(
        json.dumps(
            {
                "model_month": "2026-03",
                "evaluated_at_utc": today,
                "overall_pass": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match=r"missing DAG provenance"):
        run_promote_live._verify_cert(
            "data/analysis/backtest_reconcile",
            "2026-03",
            repo_root=tmp_path,
        )


def test_verify_cert_rejects_wrong_branch_provenance(tmp_path) -> None:
    report_dir = tmp_path / "data/analysis/backtest_reconcile"
    report_dir.mkdir(parents=True)
    today = f"{date.today().isoformat()}T12:00:00Z"
    (report_dir / run_promote_live.CERT_CHECKS_FILENAME).write_text(
        f"symbol,check_id,status,severity,evaluated_at_utc\nEURUSD,C1,pass,critical,{today}\n",
        encoding="utf-8",
    )
    (report_dir / run_promote_live.MONTHLY_RECERT_STATUS_FILENAME).write_text(
        json.dumps(
            {
                "dag_node_id": "monthly_recert",
                "model_month": "2026-03",
                "evaluated_at_utc": today,
                "overall_pass": True,
                "process_verdict": "PASS",
                "target_branch": "feature",
                "target_commit": "abc123",
                "git_dirty": False,
                "symbol_decisions": {"EURUSD": "GO"},
                "lock_fingerprint": "fp-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match=r"target_branch.*main"):
        run_promote_live._verify_cert(
            "data/analysis/backtest_reconcile",
            "2026-03",
            repo_root=tmp_path,
        )


def test_verify_dag_provenance_passes_when_certified_commit_is_current(
    tmp_path, monkeypatch
) -> None:
    """Promotion passes when current HEAD is exactly the certified commit."""
    status = _make_valid_provenance_status("2026-03")
    status["target_commit"] = "abc1234567890000000000000000000000000001"

    fake_merge_base_result = type("R", (), {
        "stdout": "abc1234567890000000000000000000000000001\n",
        "returncode": 0,
    })()
    monkeypatch.setattr(
        run_promote_live.subprocess, "run",
        lambda *args, **kwargs: fake_merge_base_result
    )

    # Should not raise
    run_promote_live._verify_dag_provenance(
        status,
        "2026-03",
        repo_root=tmp_path,
        current_commit="abc1234567890000000000000000000000000001",
    )


def test_verify_dag_provenance_passes_when_current_commit_is_descendant(
    tmp_path, monkeypatch
) -> None:
    """Promotion passes when current HEAD is a descendant of the certified commit."""
    certified = "abc1234567890000000000000000000000000001"
    current = "def9999999999999999999999999999999999002"
    status = _make_valid_provenance_status("2026-03")
    status["target_commit"] = certified

    # merge-base returns the certified commit, proving it's an ancestor
    fake_merge_base_result = type("R", (), {
        "stdout": certified + "\n",
        "returncode": 0,
    })()
    monkeypatch.setattr(
        run_promote_live.subprocess, "run",
        lambda *args, **kwargs: fake_merge_base_result
    )

    # Should not raise
    run_promote_live._verify_dag_provenance(
        status,
        "2026-03",
        repo_root=tmp_path,
        current_commit=current,
    )


def test_verify_dag_provenance_blocks_when_certified_commit_is_not_ancestor(
    tmp_path, monkeypatch
) -> None:
    """Promotion is blocked when the certified commit is not an ancestor of HEAD."""
    certified = "abc1234567890000000000000000000000000001"
    current = "def9999999999999999999999999999999999002"
    status = _make_valid_provenance_status("2026-03")
    status["target_commit"] = certified

    # merge-base returns something other than certified, proving divergence
    fake_merge_base_result = type("R", (), {
        "stdout": "0000000000000000000000000000000000000000\n",
        "returncode": 0,
    })()
    monkeypatch.setattr(
        run_promote_live.subprocess, "run",
        lambda *args, **kwargs: fake_merge_base_result
    )

    with pytest.raises(SystemExit) as exc:
        run_promote_live._verify_dag_provenance(
            status,
            "2026-03",
            repo_root=tmp_path,
            current_commit=current,
        )
    assert "abc12345" in str(exc.value)
    assert "def99999" in str(exc.value)

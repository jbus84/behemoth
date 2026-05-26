from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pytest

import scripts.run_promote_live as run_promote_live


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_valid_provenance_status(model_month: str) -> dict:
    """Create a valid monthly recert status dict for testing."""
    return {
        "dag_node_id": "monthly_recert",
        "model_month": model_month,
        "overall_pass": True,
        "process_verdict": "PASS",
        "release_decision": "GO",
        "required_go_symbols": ["EURUSD"],
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
    # v2 bundle layout: artifacts live inside the bundle
    predictions_path = build_bundle_dir / "eurusd_oco_locked_predictions.parquet"
    states_path = build_bundle_dir / "eurusd_oco_allowed_states.csv"
    predictions_path.write_text("predictions\n")
    states_path.write_text("states\n")
    model_dir = build_bundle_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    source_model_cbm = model_dir / "EURUSD_model_2026-02.cbm"
    source_threshold_json = model_dir / "EURUSD_model_2026-02.json"
    source_model_cbm.write_text("cbm\n")
    source_threshold_json.write_text('{"threshold": 1.23}\n')
    lock_path = build_bundle_dir / "eurusd_oco_live_lock.json"
    lock_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "symbol": "EURUSD",
                "artifacts": {
                    "predictions": {
                        "path": "eurusd_oco_locked_predictions.parquet",
                        "sha256": _sha256_file(predictions_path),
                    },
                    "allowed_states_csv": {
                        "path": "eurusd_oco_allowed_states.csv",
                        "sha256": _sha256_file(states_path),
                    },
                    "model_cbm": {
                        "path": "models/EURUSD_model_2026-02.cbm",
                        "sha256": _sha256_file(source_model_cbm),
                    },
                    "model_threshold_json": {
                        "path": "models/EURUSD_model_2026-02.json",
                        "sha256": _sha256_file(source_threshold_json),
                    },
                },
                "deployability": {"live_deployable": True},
                "state_universe": {"count": 7},
                "locked_runtime": {"production_cap_pips": 1.2},
            },
            indent=2,
        )
        + "\n"
    )
    archive_dir = tmp_path / "configs/research/governance/oco_history_dukascopy_candidate"
    archive_dir.mkdir(parents=True)
    (archive_dir / "stale.txt").write_text("stale\n")

    def fake_subprocess_run(args, **kwargs):
        if "rev-parse" in args:
            return type(
                "R", (), {"stdout": "abc1234567890000000000000000000000000001\n", "returncode": 0}
            )()
        return type("R", (), {"stdout": "", "returncode": 0})()

    monkeypatch.setattr(
        run_promote_live,
        "_verify_cert",
        lambda report_dir, model_month, **kwargs: verify_calls.append(
            f"{report_dir}:{model_month}"
        ),
    )
    monkeypatch.setattr(
        run_promote_live, "_load_go_symbols", lambda report_dir, model_month: ["EURUSD"]
    )
    monkeypatch.setattr(run_promote_live, "_last_complete_month", lambda override=None: "2026-02")
    monkeypatch.setattr(run_promote_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(run_promote_live.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(
        sys, "argv", ["run_promote_live.py", "--report-dir", "data/analysis/backtest_reconcile"]
    )

    run_promote_live.main()

    assert verify_calls == ["data/analysis/backtest_reconcile:2026-02"]
    promoted_lock = archive_dir / "2026-02" / "eurusd_oco_live_lock.json"
    promoted_data = json.loads(promoted_lock.read_text())
    # v2 locks are bundle-relative; paths should NOT be rewritten during promotion
    assert (
        promoted_data["artifacts"]["predictions"]["path"] == "eurusd_oco_locked_predictions.parquet"
    )
    assert (
        promoted_data["artifacts"]["allowed_states_csv"]["path"] == "eurusd_oco_allowed_states.csv"
    )

    index_path = archive_dir / "index.csv"
    assert index_path.exists()
    rows = list(csv.DictReader(index_path.open()))
    assert rows == [
        {
            "symbol": "EURUSD",
            "month": "2026-02",
            "lock_path": str(promoted_lock),
            "allowed_states_path": str(archive_dir / "2026-02" / "eurusd_oco_allowed_states.csv"),
            "model_cbm_path": str(archive_dir / "2026-02" / "models" / "EURUSD_model_2026-02.cbm"),
            "threshold_json_path": str(
                archive_dir / "2026-02" / "models" / "EURUSD_model_2026-02.json"
            ),
            "candidates_count": "7",
            "production_cap_pips": "1.2",
            "live_deployable": "True",
        }
    ]


def test_main_requires_existing_build_bundle(monkeypatch, tmp_path) -> None:
    def fake_subprocess_run(args, **kwargs):
        if "rev-parse" in args:
            return type(
                "R", (), {"stdout": "abc1234567890000000000000000000000000001\n", "returncode": 0}
            )()
        return type("R", (), {"stdout": "", "returncode": 0})()

    monkeypatch.setattr(
        run_promote_live, "_verify_cert", lambda report_dir, model_month, **kwargs: None
    )
    monkeypatch.setattr(run_promote_live, "_last_complete_month", lambda override=None: "2026-02")
    monkeypatch.setattr(run_promote_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(run_promote_live.subprocess, "run", fake_subprocess_run)
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


def test_promote_live_blocks_when_required_symbol_is_no_go(monkeypatch, tmp_path) -> None:
    build_bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-02"
    build_bundle_dir.mkdir(parents=True)
    archive_dir = tmp_path / "configs/research/governance/oco_history_dukascopy_candidate"
    active_dir = tmp_path / "configs/research/governance/oco"
    archive_dir.mkdir(parents=True)
    active_dir.mkdir(parents=True)
    (active_dir / "audusd_oco_live_lock.json").write_text("stale\n", encoding="utf-8")

    for symbol in ("EURUSD", "AUDUSD"):
        lower = symbol.lower()
        model_dir = build_bundle_dir / "models"
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
                    "schema_version": 2,
                    "symbol": symbol,
                    "artifacts": {
                        "model_cbm": {
                            "path": f"models/{symbol}_model_2026-02.cbm",
                            "sha256": _sha256_file(model_cbm),
                        },
                        "model_threshold_json": {
                            "path": f"models/{symbol}_model_2026-02.json",
                            "sha256": _sha256_file(model_thr),
                        },
                        "allowed_states_csv": {
                            "path": f"{lower}_oco_allowed_states.csv",
                            "sha256": _sha256_file(allowed_states),
                        },
                    },
                    "deployability": {"live_deployable": symbol == "EURUSD"},
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
                f"EURUSD,C1,PASS,critical,{today}",
                f"AUDUSD,C1,NO_GO,critical,{today}",
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
                "release_decision": "GO",
                "required_go_symbols": ["EURUSD", "AUDUSD"],
                "target_branch": "main",
                "target_commit": "abc1234567890000000000000000000000000001",
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

    def fake_subprocess_run(args, **kwargs):
        if "rev-parse" in args:
            return type(
                "R", (), {"stdout": "abc1234567890000000000000000000000000001\n", "returncode": 0}
            )()
        if "merge-base" in args:
            return type(
                "R", (), {"stdout": "abc1234567890000000000000000000000000001\n", "returncode": 0}
            )()
        return type("R", (), {"stdout": "", "returncode": 0})()

    monkeypatch.setattr(run_promote_live, "_last_complete_month", lambda override=None: "2026-02")
    monkeypatch.setattr(run_promote_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(run_promote_live.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(
        sys, "argv", ["run_promote_live.py", "--report-dir", "data/analysis/backtest_reconcile"]
    )

    with pytest.raises(SystemExit, match=r"required GO symbols are not GO"):
        run_promote_live.main()

    assert not (archive_dir / "2026-02" / "eurusd_oco_live_lock.json").exists()
    assert (active_dir / "audusd_oco_live_lock.json").read_text(encoding="utf-8") == "stale\n"


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
                "release_decision": "GO",
                "required_go_symbols": ["EURUSD"],
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

    fake_merge_base_result = type(
        "R",
        (),
        {
            "stdout": "abc1234567890000000000000000000000000001\n",
            "returncode": 0,
        },
    )()
    monkeypatch.setattr(
        run_promote_live.subprocess, "run", lambda *args, **kwargs: fake_merge_base_result
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
    fake_merge_base_result = type(
        "R",
        (),
        {
            "stdout": certified + "\n",
            "returncode": 0,
        },
    )()
    monkeypatch.setattr(
        run_promote_live.subprocess, "run", lambda *args, **kwargs: fake_merge_base_result
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
    fake_merge_base_result = type(
        "R",
        (),
        {
            "stdout": "0000000000000000000000000000000000000000\n",
            "returncode": 0,
        },
    )()
    monkeypatch.setattr(
        run_promote_live.subprocess, "run", lambda *args, **kwargs: fake_merge_base_result
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


def test_verify_dag_provenance_blocks_empty_target_commit(tmp_path) -> None:
    status = _make_valid_provenance_status("2026-03")
    status["target_commit"] = ""

    with pytest.raises(SystemExit, match=r"target_commit.*missing"):
        run_promote_live._verify_dag_provenance(
            status,
            "2026-03",
            repo_root=tmp_path,
            current_commit="def9999999999999999999999999999999999002",
        )


def test_main_promote_live_blocks_when_certified_commit_diverged(tmp_path, monkeypatch) -> None:
    """main() must enforce commit ancestry: if the certified commit is not an
    ancestor of current HEAD, promotion raises SystemExit."""
    import datetime

    certified = "abc1234567890000000000000000000000000001"
    current = "def9999999999999999999999999999999999002"

    # Build minimal status + CSV on disk
    status_dir = tmp_path / "data/analysis/backtest_reconcile"
    status_dir.mkdir(parents=True)
    status = _make_valid_provenance_status("2026-03")
    status["target_commit"] = certified
    status["overall_pass"] = True
    status["evaluated_at_utc"] = datetime.date.today().isoformat()
    (status_dir / "monthly_recert_status.json").write_text(json.dumps(status))
    # Minimal passing CSV
    import csv as _csv

    csv_path = status_dir / "stage14_jforex_runtime_certification_checks.csv"
    with csv_path.open("w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=["symbol", "check", "result", "evaluated_at_utc"])
        w.writeheader()
        w.writerow(
            {
                "symbol": "EURUSD",
                "check": "all",
                "result": "PASS",
                "evaluated_at_utc": datetime.date.today().isoformat(),
            }
        )

    monkeypatch.setattr(run_promote_live, "_repo_root", lambda: tmp_path)

    # git rev-parse HEAD → current (diverged from certified)
    # git merge-base certified current → unrelated base
    def fake_subprocess_run(args, **kwargs):
        if "rev-parse" in args:
            return type("R", (), {"stdout": current + "\n", "returncode": 0})()
        if "merge-base" in args:
            return type(
                "R", (), {"stdout": "0000000000000000000000000000000000000000\n", "returncode": 1}
            )()
        return type("R", (), {"stdout": "", "returncode": 0})()

    monkeypatch.setattr(run_promote_live.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_promote_live.py",
            "--report-dir",
            "data/analysis/backtest_reconcile",
            "--model-month",
            "2026-03",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        run_promote_live.main()
    assert "abc12345" in str(exc.value) or "not an ancestor" in str(exc.value)

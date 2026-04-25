from __future__ import annotations

import csv
import json
from types import SimpleNamespace

import pytest

import scripts.run_monthly_recert as run_monthly_recert


def test_main_runs_definitive_recert_chain(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []
    build_bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-02"
    build_bundle_dir.mkdir(parents=True)
    _write_bundle_fixture(build_bundle_dir)
    report_dir = "data/analysis/backtest_reconcile"
    expected_run_dir = (
        "data/analysis/backtest_reconcile/2026-02/monthly_recert"
    )

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_monthly_recert.subprocess, "run", fake_run)
    monkeypatch.setattr(run_monthly_recert, "_read_failures", lambda report_dir: {})
    monkeypatch.setattr(run_monthly_recert, "_read_acceptable_nogos", lambda report_dir: {})
    monkeypatch.setattr(
        run_monthly_recert,
        "_print_summary",
        lambda model_month, failures, acceptable_nogos=None: True,
    )
    monkeypatch.setattr(run_monthly_recert, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        run_monthly_recert,
        "_git_metadata",
        lambda: ("abc123", "main", False),
    )
    monkeypatch.setattr(run_monthly_recert, "_lock_fingerprint", lambda path: "fp-1")
    monkeypatch.setattr(
        run_monthly_recert,
        "_derive_params",
        lambda **kwargs: (
            "2026-02",
            "2026-02-04T00:00:00Z",
            "2026-02-09T00:00:00Z",
            "2026-02-07T00:00:00Z",
            "2026-02-09T00:00:00Z",
        ),
    )
    monkeypatch.setattr(
        run_monthly_recert.sys,
        "argv",
        ["run_monthly_recert.py", "--report-dir", report_dir],
    )

    run_monthly_recert.main()

    assert calls[:3] == [
        [
            "make",
            "stage13-dukascopy-cert",
            "HISTORY_DIR=configs/research/governance/oco_candidate_builds",
            f"MODELS_DIR={build_bundle_dir / 'models/oco_dukascopy_candidate'}",
            "MODEL_MONTH=2026-02",
            "PREDICTIONS_DIR=data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_m3to1_oco_fullcap",
            "START_TS=2026-02-04T00:00:00Z",
            "END_TS=2026-02-09T00:00:00Z",
            "LOCK_DIR=configs/research/governance/oco_candidate_builds/2026-02",
            f"RECONCILE_DIR={expected_run_dir}",
            f"OUT_DIR={expected_run_dir}",
        ],
        [
            "make",
            "jforex-dukascopy-matrix",
            "HISTORY_DIR=configs/research/governance/oco_candidate_builds",
            f"MODELS_DIR={build_bundle_dir / 'models/oco_dukascopy_candidate'}",
            "MODEL_MONTH=2026-02",
            "START_TS=2026-02-04T00:00:00Z",
            "END_TS=2026-02-09T00:00:00Z",
            "TICK_BATCH_SIZE=1",
            f"REPORT_DIR={expected_run_dir}",
        ],
        [
            "make",
            "local-jforex-parity-matrix",
            "HISTORY_DIR=configs/research/governance/oco_candidate_builds",
            f"MODELS_DIR={build_bundle_dir / 'models/oco_dukascopy_candidate'}",
            "MODEL_MONTH=2026-02",
            "START_TS=2026-02-07T00:00:00Z",
            "END_TS=2026-02-09T00:00:00Z",
            "TICK_BATCH_SIZE=1",
            f"REPORT_DIR={expected_run_dir}",
        ],
    ]
    assert calls[3][:2] == ["make", "full-stage14-cert"]
    assert set(calls[3][2:]) == {
        "LOCK_DIR=configs/research/governance/oco_candidate_builds/2026-02",
        f"TARGET_BUNDLE_DIR={build_bundle_dir.resolve()}",
        "TARGET_MODEL_MONTH=2026-02",
        "REQUIRE_PROVENANCE=1",
        f"RECONCILE_DIR={expected_run_dir}",
        f"OUT_CSV={expected_run_dir}/jforex_outcome_parity_summary.csv",
        f"LOCAL_SIGNAL_SUMMARY_GLOB={expected_run_dir}/*_local_jforex_signal_parity_summary.csv",
        f"LOCAL_EXECUTION_SUMMARY_GLOB={expected_run_dir}/*_local_jforex_execution_parity_summary.csv",
        f"LOCAL_LIFECYCLE_SUMMARY_GLOB={expected_run_dir}/*_local_jforex_execution_lifecycle_summary.csv",
        f"LOCAL_OPERATIONAL_SUMMARY_GLOB={expected_run_dir}/*_local_jforex_operational_ready_summary.csv",
        f"LOCAL_OUTCOME_SUMMARY_GLOB={expected_run_dir}/*_local_jforex_outcome_parity_summary.csv",
        f"LOCAL_OUT_SUMMARY_CSV={expected_run_dir}/local_jforex_surrogate_summary.csv",
        f"LOCAL_OUT_CHECKS_CSV={expected_run_dir}/local_jforex_surrogate_checks.csv",
        f"LOCAL_SURROGATE_SUMMARY_GLOB={expected_run_dir}/local_jforex_surrogate_summary.csv",
        f"STAGE13_SUMMARY_GLOB={expected_run_dir}/stage12_stage13_certification_summary.csv",
        f"JFOREX_SIGNAL_SUMMARY_GLOB={expected_run_dir}/*_jforex_signal_parity_summary.csv",
        f"JFOREX_EXECUTION_SUMMARY_GLOB={expected_run_dir}/*_jforex_execution_parity_summary.csv",
        f"JFOREX_LIFECYCLE_SUMMARY_GLOB={expected_run_dir}/*_jforex_execution_lifecycle_summary.csv",
        f"JFOREX_OPERATIONAL_SUMMARY_GLOB={expected_run_dir}/*_jforex_operational_ready_summary.csv",
        f"JFOREX_OUTCOME_SUMMARY_GLOB={expected_run_dir}/jforex_outcome_parity_summary.csv",
        f"STAGE14_OUT_SUMMARY_CSV={expected_run_dir}/stage14_jforex_runtime_certification_summary.csv",
        f"STAGE14_OUT_CHECKS_CSV={expected_run_dir}/stage14_jforex_runtime_certification_checks.csv",
        "EVAL_START=2026-02-07T00:00:00Z",
        "EVAL_END=2026-02-09T00:00:00Z",
    }

    status_path = tmp_path / expected_run_dir / run_monthly_recert.MONTHLY_RECERT_STATUS_FILENAME
    assert status_path.is_file()


def test_validate_stage14_scope_rejects_non_bundle_scoped_outputs() -> None:
    with pytest.raises(SystemExit, match=r"bundle-scoped"):
        run_monthly_recert._validate_stage14_scope(
            "data/analysis/backtest_reconcile/2026-02/monthly_recert",
            {
                "OUT_CHECKS_CSV": "data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv",
            },
        )


def test_main_requires_existing_month_bundle(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_monthly_recert, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        run_monthly_recert,
        "_derive_params",
        lambda **kwargs: (
            "2026-02",
            "2026-02-04T00:00:00Z",
            "2026-02-09T00:00:00Z",
            "2026-02-07T00:00:00Z",
            "2026-02-09T00:00:00Z",
        ),
    )
    monkeypatch.setattr(
        run_monthly_recert.sys,
        "argv",
        ["run_monthly_recert.py", "--report-dir", "data/analysis/backtest_reconcile"],
    )

    with pytest.raises(SystemExit, match=r"run make monthly-build"):
        run_monthly_recert.main()


def test_main_rejects_incomplete_month_bundle(monkeypatch, tmp_path) -> None:
    build_bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-02"
    build_bundle_dir.mkdir(parents=True)
    (build_bundle_dir / "eurusd_oco_live_lock.json").write_text("{}\n")

    monkeypatch.setattr(run_monthly_recert, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        run_monthly_recert,
        "_derive_params",
        lambda **kwargs: (
            "2026-02",
            "2026-02-04T00:00:00Z",
            "2026-02-09T00:00:00Z",
            "2026-02-07T00:00:00Z",
            "2026-02-09T00:00:00Z",
        ),
    )
    monkeypatch.setattr(
        run_monthly_recert.sys,
        "argv",
        ["run_monthly_recert.py", "--report-dir", "data/analysis/backtest_reconcile"],
    )

    with pytest.raises(SystemExit, match=r"incomplete month build bundle"):
        run_monthly_recert.main()


def test_read_failures_ignores_expected_non_deployable_nogo(tmp_path, monkeypatch) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    with (report_dir / run_monthly_recert.CERT_CHECKS_FILENAME).open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["symbol", "check_id", "status", "severity", "metric_name", "details"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "symbol": "USDCAD",
                "check_id": "LOCAL_JFOREX_SURROGATE_PASS",
                "status": "NO_GO",
                "severity": "critical",
                "metric_name": "local_jforex_surrogate_pass",
                "details": "accepted non-deployable local surrogate NO_GO (historical_deployable=false, reason=no_gate_states)",
            }
        )
        writer.writerow(
            {
                "symbol": "USDCAD",
                "check_id": "JFOREX_OUTCOME_PARITY_PASS",
                "status": "NO_GO",
                "severity": "critical",
                "metric_name": "jforex_outcome_parity_pass",
                "details": "accepted historical non-deployable NO_GO (historical_deployable=false, reason=no_gate_states)",
            }
        )
    monkeypatch.setattr(run_monthly_recert, "_repo_root", lambda: tmp_path)

    failures = run_monthly_recert._read_failures("reports")
    acceptable_nogos = run_monthly_recert._read_acceptable_nogos("reports")

    assert failures == {}
    assert list(acceptable_nogos) == ["USDCAD"]
    assert {row["check_id"] for row in acceptable_nogos["USDCAD"]} == {
        "LOCAL_JFOREX_SURROGATE_PASS",
        "JFOREX_OUTCOME_PARITY_PASS",
    }


def test_print_summary_keeps_go_when_only_expected_nogo_remains(capsys) -> None:
    overall_pass = run_monthly_recert._print_summary(
        "2026-02",
        {},
        {
            "USDCAD": [
                {
                    "check_id": "LOCAL_JFOREX_SURROGATE_PASS",
                    "details": "accepted non-deployable local surrogate NO_GO (historical_deployable=false, reason=no_gate_states)",
                }
            ]
        },
    )

    out = capsys.readouterr().out
    assert overall_pass is True
    assert "USDCAD  NOGO" in out
    assert "go/no-go: GO" in out


def _write_bundle_fixture(build_bundle_dir) -> None:
    bundle_root = build_bundle_dir.parent
    model_dir = build_bundle_dir / "models/oco_dukascopy_candidate"
    model_dir.mkdir(parents=True)
    rows = []
    for symbol in run_monthly_recert.DEFAULT_SYMBOLS:
        lower = symbol.lower()
        cbm_path = model_dir / f"{symbol}_model_2026-02.cbm"
        thr_path = model_dir / f"{symbol}_model_2026-02.json"
        cbm_path.write_text("cbm\n")
        thr_path.write_text('{"threshold": 1.23}\n')
        lock_path = build_bundle_dir / f"{lower}_oco_live_lock.json"
        lock_path.write_text(
            json.dumps(
                {
                    "symbol": symbol,
                    "artifacts": {
                        "model_cbm_path": str(cbm_path),
                        "model_threshold_json_path": str(thr_path),
                    },
                }
            )
            + "\n"
        )
        rows.append(
            {
                "symbol": symbol,
                "month": "2026-02",
                "lock_path": str(lock_path),
                "allowed_states_path": str(build_bundle_dir / f"{lower}_oco_allowed_states.csv"),
                "model_cbm_path": str(cbm_path),
                "threshold_json_path": str(thr_path),
                "candidates_count": 1,
                "production_cap_pips": 1.2,
                "live_deployable": True,
            }
        )
    index_path = bundle_root / "index.csv"
    with index_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "month",
                "lock_path",
                "allowed_states_path",
                "model_cbm_path",
                "threshold_json_path",
                "candidates_count",
                "production_cap_pips",
                "live_deployable",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_write_recert_status_records_dag_provenance(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_monthly_recert, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        run_monthly_recert,
        "_git_metadata",
        lambda: ("abc123", "main", False),
    )
    monkeypatch.setattr(run_monthly_recert, "_lock_fingerprint", lambda path: "fp-1")

    report_dir = "data/analysis/backtest_reconcile/2026-03/monthly_recert"
    summary_dir = tmp_path / report_dir
    summary_dir.mkdir(parents=True)
    (summary_dir / run_monthly_recert.CERT_SUMMARY_FILENAME).write_text(
        "symbol,process_status,go_decision\nEURUSD,PASS,GO\nAUDUSD,PASS,NO_GO\n",
        encoding="utf-8",
    )

    run_monthly_recert._write_recert_status(
        "2026-03",
        report_dir,
        run_monthly_recert.Path("configs/research/governance/oco_candidate_builds/2026-03"),
        True,
    )

    payload = json.loads(
        (summary_dir / run_monthly_recert.MONTHLY_RECERT_STATUS_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert payload["dag_node_id"] == "monthly_recert"
    assert payload["target_branch"] == "main"
    assert payload["target_commit"] == "abc123"
    assert payload["git_dirty"] is False
    assert payload["process_verdict"] == "PASS"
    assert payload["symbol_decisions"] == {"AUDUSD": "NO_GO", "EURUSD": "GO"}
    assert payload["lock_fingerprint"] == "fp-1"

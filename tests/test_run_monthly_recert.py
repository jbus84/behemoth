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

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_monthly_recert.subprocess, "run", fake_run)
    monkeypatch.setattr(run_monthly_recert, "_read_failures", lambda report_dir: {})
    monkeypatch.setattr(run_monthly_recert, "_print_summary", lambda model_month, failures: True)
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

    run_monthly_recert.main()

    assert calls == [
        [
            "make",
            "jforex-dukascopy-matrix",
            "HISTORY_DIR=configs/research/governance/oco_candidate_builds",
            f"MODELS_DIR={build_bundle_dir / 'models/oco_dukascopy_candidate'}",
            "MODEL_MONTH=2026-02",
            "START_TS=2026-02-04T00:00:00Z",
            "END_TS=2026-02-09T00:00:00Z",
            "TICK_BATCH_SIZE=1",
        ],
        [
            "make",
            "stage13-dukascopy-cert",
            "LOCK_DIR=configs/research/governance/oco_candidate_builds/2026-02",
            "RECONCILE_DIR=data/analysis/backtest_reconcile",
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
        ],
        [
            "make",
            "full-stage14-cert",
            "LOCK_DIR=configs/research/governance/oco_candidate_builds/2026-02",
            "EVAL_START=2026-02-07T00:00:00Z",
            "EVAL_END=2026-02-09T00:00:00Z",
        ],
    ]


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

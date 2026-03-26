from __future__ import annotations

from types import SimpleNamespace

import pytest

import scripts.run_monthly_recert as run_monthly_recert


def test_main_runs_definitive_recert_chain(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []
    build_bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-02"
    build_bundle_dir.mkdir(parents=True)

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
            "MODEL_MONTH=2026-02",
            "START_TS=2026-02-04T00:00:00Z",
            "END_TS=2026-02-09T00:00:00Z",
            "TICK_BATCH_SIZE=1",
        ],
        [
            "make",
            "local-jforex-parity-matrix",
            "HISTORY_DIR=configs/research/governance/oco_candidate_builds",
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

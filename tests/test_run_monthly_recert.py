from __future__ import annotations

from types import SimpleNamespace

import scripts.run_monthly_recert as run_monthly_recert


def test_main_runs_definitive_recert_chain(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_monthly_recert.subprocess, "run", fake_run)
    monkeypatch.setattr(run_monthly_recert, "_read_failures", lambda report_dir: {})
    monkeypatch.setattr(run_monthly_recert, "_print_summary", lambda model_month, failures: True)
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
            "uv",
            "run",
            "python",
            "scripts/sync_candidate_model_artifacts.py",
            "--lock-dir",
            "configs/research/governance/oco",
            "--source-models-dir",
            "models/oco",
            "--target-models-dir",
            "models/oco_dukascopy_candidate",
            "--symbols",
            "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
        ],
        [
            "make",
            "jforex-dukascopy-matrix",
            "MODEL_MONTH=2026-02",
            "START_TS=2026-02-04T00:00:00Z",
            "END_TS=2026-02-09T00:00:00Z",
            "TICK_BATCH_SIZE=1",
        ],
        [
            "make",
            "local-jforex-parity-matrix",
            "MODEL_MONTH=2026-02",
            "START_TS=2026-02-04T00:00:00Z",
            "END_TS=2026-02-09T00:00:00Z",
            "TICK_BATCH_SIZE=1",
        ],
        [
            "make",
            "full-stage14-cert",
            "LOCK_DIR=configs/research/governance/oco_history_dukascopy_candidate/2026-02",
            "EVAL_START=2026-02-07T00:00:00Z",
            "EVAL_END=2026-02-09T00:00:00Z",
        ],
    ]

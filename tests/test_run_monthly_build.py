from __future__ import annotations

from types import SimpleNamespace

import scripts.run_monthly_build as run_monthly_build


def test_main_builds_candidate_month_bundle(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_monthly_build.subprocess, "run", fake_run)
    monkeypatch.setattr(
        run_monthly_build,
        "_derive_model_month",
        lambda override=None: "2026-02",
    )
    monkeypatch.setattr(
        run_monthly_build.sys,
        "argv",
        ["run_monthly_build.py"],
    )

    run_monthly_build.main()

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
            "uv",
            "run",
            "python",
            "scripts/freeze_oco_historical_governance.py",
            "--symbols",
            "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
            "--out-dir",
            "configs/research/governance/oco_candidate_builds",
            "--months",
            "2026-02",
            "--config-dir",
            "configs/research/experiments_dukascopy_candidate",
            "--analysis-dir",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate",
            "--models-dir",
            "models/oco_dukascopy_candidate",
        ],
    ]

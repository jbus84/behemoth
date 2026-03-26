from __future__ import annotations

from types import SimpleNamespace

import scripts.run_promote_live as run_promote_live


def test_main_archives_candidate_models_dir(monkeypatch) -> None:
    calls: list[list[str]] = []
    verify_calls: list[str] = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_promote_live.subprocess, "run", fake_run)
    monkeypatch.setattr(run_promote_live, "_verify_cert", lambda report_dir: verify_calls.append(report_dir))
    monkeypatch.setattr(run_promote_live, "_last_complete_month", lambda override=None: "2026-02")
    monkeypatch.setattr(
        run_promote_live.sys,
        "argv",
        ["run_promote_live.py", "--report-dir", "data/analysis/backtest_reconcile"],
    )

    run_promote_live.main()

    assert verify_calls == ["data/analysis/backtest_reconcile"]
    assert calls == [
        [
            run_promote_live.sys.executable,
            "scripts/freeze_oco_historical_governance.py",
            "--symbols",
            "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
            "--out-dir",
            "configs/research/governance/oco_history_dukascopy_candidate",
            "--months",
            "2026-02",
            "--config-dir",
            "configs/research/experiments_dukascopy_candidate",
            "--analysis-dir",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate",
            "--models-dir",
            "models/oco_dukascopy_candidate",
        ]
    ]

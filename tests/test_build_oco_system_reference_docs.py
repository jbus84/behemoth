from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.build_oco_system_reference_docs import PAGES, run


def test_build_system_reference_docs_writes_all_pages_and_status(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir(parents=True, exist_ok=True)

    analysis_root = tmp_path / "data" / "analysis"
    tick_root = analysis_root / "tick_opportunity_mining"
    tick_root.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {"symbol": "EURUSD", "test_month": "2025-12", "fill_rate": 0.99, "overshoot_p95_pips": 0.3},
            {"symbol": "GBPUSD", "test_month": "2025-12", "fill_rate": 0.98, "overshoot_p95_pips": 0.4},
            {"symbol": "USDJPY", "test_month": "2025-12", "fill_rate": 0.97, "overshoot_p95_pips": 0.5},
        ]
    ).to_csv(tick_root / "oco_execution_drift_monthly.csv", index=False)
    pd.DataFrame(
        [
            {"symbol": "EURUSD", "quantile": 0.9, "final_score": 1.0, "is_current_policy": 1, "w13_threshold_fragility": 1.0},
            {"symbol": "GBPUSD", "quantile": 0.9, "final_score": 1.0, "is_current_policy": 1, "w13_threshold_fragility": 1.1},
            {"symbol": "USDJPY", "quantile": 0.9, "final_score": 1.0, "is_current_policy": 1, "w13_threshold_fragility": 1.2},
        ]
    ).to_csv(tick_root / "oco_threshold_sensitivity.csv", index=False)
    pd.DataFrame([{"symbol": "EURUSD", "scenario_id": "S1_mild", "lb95_per_signal_pips": 0.4}]).to_csv(
        tick_root / "execution_mc_symbol_scenarios.csv",
        index=False,
    )
    pd.DataFrame([{"check_id": "C0", "status": "pass", "severity_if_fail": "low", "metric_value": 0.0}]).to_csv(
        tick_root / "docs_contract_checks.csv",
        index=False,
    )
    pd.DataFrame([{"baseline_run_id": "a", "latest_run_id": "a", "metric_rows_changed": 0, "gate_rows_changed": 0}]).to_csv(
        tick_root / "run_delta_summary.csv",
        index=False,
    )
    pd.DataFrame(columns=["symbol", "metric_id", "band"]).to_csv(tick_root / "operator_action_status.csv", index=False)
    pd.DataFrame(columns=["symbol", "metric_id", "band"]).to_csv(tick_root / "oco_alert_disposition.csv", index=False)

    out_status_csv = tick_root / "system_reference_build_status.csv"
    out = run(docs_root=docs_root, analysis_root=analysis_root, out_status_csv=out_status_csv)

    assert len(out) == len(PAGES)
    assert out_status_csv.exists()

    for spec in PAGES:
        p = docs_root / str(spec["path"])
        assert p.exists()
        txt = p.read_text(encoding="utf-8")
        key = str(spec["key"])
        assert f"<!-- GENERATED:SYSREF:{key}:START -->" in txt
        assert f"<!-- GENERATED:SYSREF:{key}:END -->" in txt
        assert "- symbols_covered: `EURUSD,GBPUSD,USDJPY`" in txt

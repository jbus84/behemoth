from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.build_oco_threshold_sensitivity_report import SymbolPaths, run


def _write_symbol_pred(path: Path, symbol: str) -> None:
    rows = []
    months = ["2025-01", "2025-02", "2025-03", "2025-04"]
    for i, m in enumerate(months):
        for j in range(60):
            p = 0.40 + 0.01 * (j % 20) + 0.02 * i
            gross = 0.2 + 0.03 * (j % 10) + 0.02 * i
            rows.append(
                {
                    "test_month": m,
                    "close_ts": f"{m}-01T00:{j % 60:02d}:00Z",
                    "pred_prob": min(0.99, p),
                    "target_gross_pips": gross,
                }
            )
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_lock(path: Path) -> None:
    obj = {
        "locked_runtime": {"rolling_threshold_days": 20},
        "retrain_policy": {"cadence_days": 30, "window_days": 3, "anchor_day_utc": 1},
    }
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_threshold_sensitivity_report_outputs(tmp_path: Path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("cadence_days: 30\nwindow_days: 3\nanchor_day_utc: 1\n", encoding="utf-8")
    symbol_paths: dict[str, SymbolPaths] = {}
    for sym in ["EURUSD", "GBPUSD", "USDJPY"]:
        pred = tmp_path / f"{sym}_pred.parquet"
        lock = tmp_path / f"{sym}_lock.json"
        _write_symbol_pred(pred, sym)
        _write_lock(lock)
        symbol_paths[sym] = SymbolPaths(symbol=sym, pred_path=pred, lock_path=lock)

    sens, alerts = run(
        symbols=["EURUSD", "GBPUSD", "USDJPY"],
        lookback_days=[10, 20],
        cadence_days=[14, 30],
        window_days=[2, 3],
        quantile=0.9,
        quantile_delta=0.02,
        min_history=30,
        governance_policy_yaml=policy,
        symbol_paths=symbol_paths,
        out_sensitivity_csv=tmp_path / "sensitivity.csv",
        out_alerts_csv=tmp_path / "alerts.csv",
        report_out=tmp_path / "report.md",
    )
    assert not sens.empty
    assert not alerts.empty
    assert {
        "symbol",
        "lookback_days",
        "cadence_days",
        "window_days",
        "final_score",
        "is_recommended",
        "is_current_policy",
    }.issubset(set(sens.columns))
    for sym in ["EURUSD", "GBPUSD", "USDJPY"]:
        g = sens[sens["symbol"] == sym]
        assert int(g["is_recommended"].sum()) >= 1
        assert int(g["is_current_policy"].sum()) >= 1

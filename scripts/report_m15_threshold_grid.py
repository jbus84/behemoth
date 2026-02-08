#!/usr/bin/env python3
"""
Report M15 holdout threshold stats on the trained CatBoost model.

Outputs gross and cost-adjusted metrics for:
- Sample-level rows by strategy_type (MOM / REV)
- Event-level best-of-two selections (max pred per pair,timestamp)
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostRegressor

DATA_PATH = "data/meta_model/events_m15_8yr_v3_dual.csv"
MODEL_PATH = "models/meta_model_m15/catboost_m15_reg.cbm"
OUT_DIR = "data/analysis"

CATEGORICAL_FEATURES = ["strategy_type", "active_leg", "side"]
NUMERIC_FEATURES = [
    "z_entry",
    "z_velocity",
    "spread_std",
    "beta_stability",
    "beta",
    "signal_beta_lookback",
    "hedge_beta_lookback",
    "beta_mismatch",
    "vol_ratio",
    "correlation_500",
    "trend_strength",
    "hour",
    "day_of_week",
    "ret_X_16b",
    "ret_Y_16b",
    "atr_ratio",
    "entry_atr",
    "vol_regime",
]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

THRESHOLDS = [5, 8, 10, 12, 15, 18, 20, 25, 30]
COST_SCENARIOS_BPS = [3, 5, 9]


def _metric_row(sub: pd.DataFrame, threshold: int, bucket: str, level: str, cost_bps: int) -> dict[str, object]:
    pnl = sub["pnl_bps"].to_numpy()
    n = len(sub)
    gross_win = float((pnl > 0).mean() * 100.0) if n else 0.0
    gross_mean = float(pnl.mean()) if n else 0.0
    gross_total = float(pnl.sum()) if n else 0.0

    net = pnl - cost_bps if n else pnl
    net_win = float((net > 0).mean() * 100.0) if n else 0.0
    net_mean = float(net.mean()) if n else 0.0
    net_total = float(net.sum()) if n else 0.0

    return {
        "level": level,
        "bucket": bucket,
        "pred_threshold": threshold,
        "cost_bps": cost_bps,
        "trades": n,
        "gross_win_rate_pct": gross_win,
        "gross_mean_pnl_bps": gross_mean,
        "gross_total_pnl_bps": gross_total,
        "net_win_rate_pct": net_win,
        "net_mean_pnl_bps": net_mean,
        "net_total_pnl_bps": net_total,
    }


def _run_level(df_test: pd.DataFrame, level: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for threshold in THRESHOLDS:
        filtered = df_test[df_test["pred_pnl"] > threshold]
        for bucket in ["ALL", "MOM", "REV"]:
            if bucket == "ALL":
                sub = filtered
            else:
                sub = filtered[filtered["strategy_type"] == bucket]
            for cost in COST_SCENARIOS_BPS:
                rows.append(_metric_row(sub, threshold, bucket, level, cost))
    return pd.DataFrame(rows)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    df = pl.read_csv(DATA_PATH).to_pandas()
    df_test = df[df["year"] >= 2024].copy()

    model = CatBoostRegressor()
    model.load_model(MODEL_PATH)
    model_features = list(getattr(model, "feature_names_", [])) or [f for f in ALL_FEATURES if f in df_test.columns]
    df_test["pred_pnl"] = model.predict(df_test[model_features])

    sample_df = _run_level(df_test, level="sample")
    sample_out = os.path.join(OUT_DIR, "m15_threshold_grid_sample_by_type.csv")
    sample_df.to_csv(sample_out, index=False)

    idx = df_test.groupby(["pair", "timestamp"])["pred_pnl"].idxmax()
    event_df = df_test.loc[idx].copy()
    event_metrics = _run_level(event_df, level="event_best_of_two")
    event_out = os.path.join(OUT_DIR, "m15_threshold_grid_event_by_type.csv")
    event_metrics.to_csv(event_out, index=False)

    # concise console summary for recommended thresholds
    focus = sample_df[
        (sample_df["bucket"] == "ALL")
        & (sample_df["cost_bps"] == 5)
        & (sample_df["pred_threshold"].isin([8, 10, 12, 15]))
    ].sort_values("pred_threshold")
    print("\nM15 sample-level focus (ALL, cost=5bps):")
    print(
        focus[
            [
                "pred_threshold",
                "trades",
                "gross_win_rate_pct",
                "gross_mean_pnl_bps",
                "net_win_rate_pct",
                "net_mean_pnl_bps",
            ]
        ].to_string(index=False)
    )

    print(f"\nSaved:\n- {sample_out}\n- {event_out}")


if __name__ == "__main__":
    main()

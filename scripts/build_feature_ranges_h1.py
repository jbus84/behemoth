#!/usr/bin/env python3
"""
Build feature range baselines for H1 meta model (training years only).
Outputs JSON with p01/p99 bounds for numeric features.
"""

import json
import os
import polars as pl

DATA_PATH = "data/meta_model/events_h1_8yr_v3_dual.csv"
OUT_PATH = "models/meta_model_h1/feature_ranges_h1.json"

NUMERIC_FEATURES = [
    'z_entry', 'z_velocity', 'spread_std', 'beta_stability', 'beta',
    'signal_beta_lookback', 'hedge_beta_lookback', 'beta_mismatch',
    'vol_ratio', 'correlation_500', 'trend_strength', 'hour', 'day_of_week',
    'ret_X_16b', 'ret_Y_16b', 'atr_ratio', 'entry_atr', 'vol_regime'
]

TRAIN_END_YEAR = 2023


def main():
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(DATA_PATH)

    df = pl.read_csv(DATA_PATH)
    train_df = df.filter(pl.col('year') <= TRAIN_END_YEAR)

    stats = {
        "source": DATA_PATH,
        "train_years": f"2018-{TRAIN_END_YEAR}",
        "features": {},
    }

    for f in NUMERIC_FEATURES:
        if f not in train_df.columns:
            print(f"Skipping missing feature: {f}")
            continue
        s = train_df.select(pl.col(f))
        p01 = train_df.select(pl.col(f).quantile(0.01, "linear")).item()
        p99 = train_df.select(pl.col(f).quantile(0.99, "linear")).item()
        mean = train_df.select(pl.col(f).mean()).item()
        std = train_df.select(pl.col(f).std()).item()
        fmin = train_df.select(pl.col(f).min()).item()
        fmax = train_df.select(pl.col(f).max()).item()

        stats["features"][f] = {
            "p01": float(p01),
            "p99": float(p99),
            "mean": float(mean),
            "std": float(std),
            "min": float(fmin),
            "max": float(fmax),
        }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, sort_keys=True)

    print(f"Saved feature ranges to {OUT_PATH}")


if __name__ == "__main__":
    main()

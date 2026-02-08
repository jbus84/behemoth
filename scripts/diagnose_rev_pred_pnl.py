#!/usr/bin/env python3
"""
Diagnose REV expected value:
- Fit two-stage (clf + reg) on REV rows
- Compare predicted PnL distribution vs realized PnL (holdout)

Outputs:
- data/analysis/<bar>_rev_pred_vs_real_holdout.csv
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier, CatBoostRegressor, Pool

DATA_PATHS = {
    "m30": "data/meta_model/events_m30_8yr_v3_dual.csv",
    "h1": "data/meta_model/events_h1_8yr_v3_dual.csv",
}

CATEGORICAL_FEATURES = ["active_leg", "side"]
NUMERIC_FEATURES = [
    "z_entry",
    "z_velocity",
    "z_lag1",
    "z_lag2",
    "z_lag3",
    "dz_lag1",
    "dz_lag2",
    "spread_std",
    "beta_stability",
    "beta",
    "beta_lag1",
    "beta_lag2",
    "signal_beta_lookback",
    "hedge_beta_lookback",
    "beta_mismatch",
    "vol_ratio",
    "correlation_500",
    "trend_strength",
    "hour",
    "day_of_week",
    "ret_X_1h",
    "ret_Y_1h",
    "ret_X_16b",
    "ret_Y_16b",
    "ret_X_4h",
    "ret_Y_4h",
    "atr_ratio",
    "entry_atr",
    "vol_regime",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

CLF_PARAMS = dict(
    iterations=1200,
    depth=7,
    learning_rate=0.03,
    loss_function="Logloss",
    verbose=False,
    random_seed=42,
)
REG_PARAMS = dict(
    iterations=1200,
    depth=7,
    learning_rate=0.03,
    loss_function="RMSE",
    verbose=False,
    random_seed=42,
)


def _fit_models(
    train: pd.DataFrame, test: pd.DataFrame
) -> tuple[CatBoostClassifier, CatBoostRegressor, list[str]]:
    use_features = [f for f in FEATURES if f in train.columns]
    cat_idx = [train[use_features].columns.get_loc(c) for c in CATEGORICAL_FEATURES if c in use_features]

    clf = CatBoostClassifier(**CLF_PARAMS)
    clf.fit(
        Pool(train[use_features], (train["pnl_bps"] > 0).astype(int), cat_features=cat_idx),
        eval_set=Pool(test[use_features], (test["pnl_bps"] > 0).astype(int), cat_features=cat_idx),
        early_stopping_rounds=80,
    )

    reg_pnl = CatBoostRegressor(**REG_PARAMS)
    reg_pnl.fit(
        Pool(train[use_features], train["pnl_bps"], cat_features=cat_idx),
        eval_set=Pool(test[use_features], test["pnl_bps"], cat_features=cat_idx),
        early_stopping_rounds=80,
    )
    return clf, reg_pnl, use_features


def _summary(series: pd.Series) -> dict[str, float]:
    return {
        "count": float(series.count()),
        "mean": float(series.mean()) if len(series) else 0.0,
        "median": float(series.median()) if len(series) else 0.0,
        "p10": float(series.quantile(0.10)) if len(series) else 0.0,
        "p25": float(series.quantile(0.25)) if len(series) else 0.0,
        "p75": float(series.quantile(0.75)) if len(series) else 0.0,
        "p90": float(series.quantile(0.90)) if len(series) else 0.0,
        "min": float(series.min()) if len(series) else 0.0,
        "max": float(series.max()) if len(series) else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bar", choices=["m30", "h1"], default="m30")
    args = parser.parse_args()

    out_dir = Path("data/analysis")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pl.read_csv(DATA_PATHS[args.bar]).to_pandas()
    rev = df[df["strategy_type"] == "REV"].copy()

    train = rev[rev["year"] <= 2023].copy()
    test = rev[rev["year"] >= 2024].copy()

    clf, reg_pnl, use_features = _fit_models(train, test)
    pred = test.copy()
    pred["p_up"] = clf.predict_proba(pred[use_features])[:, 1]
    pred["pred_pnl"] = reg_pnl.predict(pred[use_features])

    out_path = out_dir / f"{args.bar}_rev_pred_vs_real_holdout.csv"
    pred[["pair", "timestamp", "year", "pnl_bps", "pred_pnl", "p_up", "outcome"]].to_csv(out_path, index=False)

    realized = pred["pnl_bps"]
    predicted = pred["pred_pnl"]

    corr = float(np.corrcoef(realized, predicted)[0, 1]) if len(pred) > 1 else 0.0
    pos_frac = float((predicted > 0).mean() * 100.0) if len(pred) else 0.0

    print(f"\n{args.bar.upper()} REV holdout diagnostics (2024–2025)")
    print("Predicted PnL summary:", _summary(predicted))
    print("Realized PnL summary:", _summary(realized))
    print(f"Pred>0 fraction: {pos_frac:.2f}%")
    print(f"Pred vs Real correlation: {corr:.4f}")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

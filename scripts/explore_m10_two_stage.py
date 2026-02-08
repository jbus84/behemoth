#!/usr/bin/env python3
"""
M10 two-stage exploration (MOM or REV).
- Stage 1: classifier predicts win probability for selected strategy
- Stage 2: regressor predicts signed PnL
- Edge = pred_pnl (expected value)

Outputs:
- data/analysis/m10_two_stage_holdout_thresholds_<strategy>.csv
- data/analysis/m10_two_stage_wfo_thresholds_<strategy>.csv
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier, CatBoostRegressor, Pool

DATA_PATH = "data/meta_model/events_m10_8yr_v3_dual.csv"
OUT_DIR = "data/analysis"

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
    "atr_ratio",
    "entry_atr",
    "vol_regime",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

EDGE_THRESHOLDS = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6, 7, 8, 9, 10]
COSTS_BPS = [3, 5, 9]

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


def _predict(
    df: pd.DataFrame, clf: CatBoostClassifier, reg_pnl: CatBoostRegressor, use_features: list[str]
) -> pd.DataFrame:
    out = df.copy()
    out["p_up"] = clf.predict_proba(out[use_features])[:, 1]
    out["pred_pnl"] = reg_pnl.predict(out[use_features])
    out["edge_score"] = out["pred_pnl"]
    return out


def _threshold_rows(df: pd.DataFrame, with_year: bool = False) -> pd.DataFrame:
    rows: list[dict[str, float | int]] = []
    for t in EDGE_THRESHOLDS:
        sub = df[(df["edge_score"] > t) & (df["p_up"] >= 0.5)]
        pnl = sub["pnl_bps"].to_numpy()
        for cost in COSTS_BPS:
            net = pnl - cost if len(pnl) else pnl
            row = {
                "edge_threshold": t,
                "cost_bps": cost,
                "trades": len(sub),
                "gross_win_rate_pct": float((pnl > 0).mean() * 100.0) if len(pnl) else 0.0,
                "gross_mean_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "gross_total_pnl_bps": float(pnl.sum()) if len(pnl) else 0.0,
                "net_win_rate_pct": float((net > 0).mean() * 100.0) if len(net) else 0.0,
                "net_mean_pnl_bps": float(net.mean()) if len(net) else 0.0,
                "net_total_pnl_bps": float(net.sum()) if len(net) else 0.0,
            }
            if with_year and "year" in sub.columns:
                row["year"] = int(sub["year"].iloc[0]) if len(sub) else -1
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["MOM", "REV"], default="MOM")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    df = pl.read_csv(DATA_PATH).to_pandas()
    data = df[df["strategy_type"] == args.strategy].copy()

    train = data[data["year"] <= 2023].copy()
    test = data[data["year"] >= 2024].copy()

    clf, reg_pnl, use_features = _fit_models(train, test)
    holdout_pred = _predict(test, clf, reg_pnl, use_features)
    holdout_rows = _threshold_rows(holdout_pred)
    holdout_out = os.path.join(OUT_DIR, f"m10_two_stage_holdout_thresholds_{args.strategy.lower()}.csv")
    holdout_rows.to_csv(holdout_out, index=False)

    wfo_frames = []
    for year in [2022, 2023, 2024, 2025]:
        tr = data[data["year"] < year].copy()
        te = data[data["year"] == year].copy()
        if len(tr) < 10000 or len(te) < 1000:
            continue
        clf_y, reg_y, feat_y = _fit_models(tr, te)
        pred = _predict(te, clf_y, reg_y, feat_y)
        rows = _threshold_rows(pred, with_year=True)
        rows["test_year"] = year
        wfo_frames.append(rows)

    wfo_df = pd.concat(wfo_frames, ignore_index=True) if wfo_frames else pd.DataFrame()
    wfo_out = os.path.join(OUT_DIR, f"m10_two_stage_wfo_thresholds_{args.strategy.lower()}.csv")
    wfo_df.to_csv(wfo_out, index=False)

    summary_edges = [0, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5]
    view = holdout_rows[
        (holdout_rows["cost_bps"] == 5) & (holdout_rows["edge_threshold"].isin(summary_edges))
    ][
        [
            "edge_threshold",
            "trades",
            "gross_win_rate_pct",
            "gross_mean_pnl_bps",
            "net_win_rate_pct",
            "net_mean_pnl_bps",
            "net_total_pnl_bps",
        ]
    ]
    print(f"\nM10 {args.strategy} two-stage holdout (cost=5bps, selected edges):")
    print(view.to_string(index=False))
    print(f"\nSaved:\n- {holdout_out}\n- {wfo_out}")


if __name__ == "__main__":
    main()

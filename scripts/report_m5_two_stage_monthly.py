#!/usr/bin/env python3
"""
Monthly breakdown for M5 two-stage model (gross + net).
Uses |edge_score| from the two-stage outputs.
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier, CatBoostRegressor, Pool

DATA_PATH = "data/meta_model/events_m5_8yr_v3_dual.csv"
OUT_PATH = "data/analysis/m5_two_stage_monthly_thresholds.csv"

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

EDGE_THRESHOLDS = [0, 1, 2, 3, 4, 5]
COST_BPS = 5

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


def _fit_two_stage(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
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

    out = test.copy()
    out["p_up"] = clf.predict_proba(out[use_features])[:, 1]
    out["pred_pnl"] = reg_pnl.predict(out[use_features])
    choose_mom = out["p_up"] >= 0.5
    out["chosen_pnl_bps"] = np.where(choose_mom, out["pnl_bps"], -out["pnl_bps"])
    out["edge_score"] = out["pred_pnl"]
    return out


def main() -> None:
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df = pl.read_csv(DATA_PATH).to_pandas()

    mom = df[df["strategy_type"] == "MOM"].copy()
    train = mom[mom["year"] <= 2023].copy()
    test = mom[mom["year"] >= 2024].copy()

    pred = _fit_two_stage(train, test)
    pred["timestamp"] = pd.to_datetime(pred["timestamp"], errors="coerce")
    pred = pred.dropna(subset=["timestamp"])
    pred["month"] = pred["timestamp"].dt.strftime("%Y-%m")

    rows = []
    for month, sub in pred.groupby("month"):
        for t in EDGE_THRESHOLDS:
            filt = sub[np.abs(sub["edge_score"]) > t]
            pnl = filt["chosen_pnl_bps"].to_numpy()
            n = len(pnl)
            if n:
                gross_wr = float((pnl > 0).mean() * 100.0)
                gross_mean = float(pnl.mean())
                gross_total = float(pnl.sum())
                net = pnl - COST_BPS
                net_wr = float((net > 0).mean() * 100.0)
                net_mean = float(net.mean())
                net_total = float(net.sum())
            else:
                gross_wr = gross_mean = gross_total = 0.0
                net_wr = net_mean = net_total = 0.0

            rows.append(
                {
                    "month": month,
                    "edge_threshold": t,
                    "trades": n,
                    "gross_win_rate_pct": gross_wr,
                    "gross_mean_pnl_bps": gross_mean,
                    "gross_total_pnl_bps": gross_total,
                    "net_win_rate_pct": net_wr,
                    "net_mean_pnl_bps": net_mean,
                    "net_total_pnl_bps": net_total,
                }
            )

    out = pd.DataFrame(rows).sort_values(["month", "edge_threshold"])
    out.to_csv(OUT_PATH, index=False)
    print(f"Saved {OUT_PATH}")


if __name__ == "__main__":
    main()

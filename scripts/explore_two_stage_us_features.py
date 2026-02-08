#!/usr/bin/env python3
"""
Two-stage model with US-session and regime-shift features.
Outputs holdout thresholds to data/analysis for M5 or M15.
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier, CatBoostRegressor, Pool

DATA_PATHS = {
    "m5": "data/meta_model/events_m5_8yr_v3_dual.csv",
    "m15": "data/meta_model/events_m15_8yr_v3_dual.csv",
}
OUT_DIR = "data/analysis"

CATEGORICAL_FEATURES = ["active_leg", "side"]
BASE_NUMERIC_FEATURES = [
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

EDGE_THRESHOLDS = [0, 1, 2, 3, 4, 5, 7, 10]
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


def _compute_regime_stats(train: pd.DataFrame) -> dict[str, float]:
    stats = {}
    for col in ["vol_ratio", "spread_std", "entry_atr"]:
        series = train[col].dropna()
        stats[f"{col}_p10"] = float(series.quantile(0.10))
        stats[f"{col}_p90"] = float(series.quantile(0.90))
    return stats


def _add_us_features(df: pd.DataFrame, stats: dict[str, float]) -> pd.DataFrame:
    out = df.copy()
    hour = out["hour"].astype(int)
    is_us = (hour >= 13) & (hour < 21)
    out["is_us_session"] = is_us.astype(int)
    out["is_us_open"] = (hour == 13).astype(int)
    out["is_us_close"] = (hour == 20).astype(int)
    out["is_london_ny_overlap"] = ((hour >= 13) & (hour < 16)).astype(int)
    out["us_session_progress"] = np.where(is_us, (hour - 13) / 8.0, 0.0)

    out["vol_ratio_hi"] = (out["vol_ratio"] > stats["vol_ratio_p90"]).astype(int)
    out["vol_ratio_lo"] = (out["vol_ratio"] < stats["vol_ratio_p10"]).astype(int)
    out["spread_std_hi"] = (out["spread_std"] > stats["spread_std_p90"]).astype(int)
    out["entry_atr_hi"] = (out["entry_atr"] > stats["entry_atr_p90"]).astype(int)
    return out


def _fit_two_stage(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    stats = _compute_regime_stats(train)
    train = _add_us_features(train, stats)
    test = _add_us_features(test, stats)

    extra_features = [
        "is_us_session",
        "is_us_open",
        "is_us_close",
        "is_london_ny_overlap",
        "us_session_progress",
        "vol_ratio_hi",
        "vol_ratio_lo",
        "spread_std_hi",
        "entry_atr_hi",
    ]
    use_features = [f for f in (CATEGORICAL_FEATURES + BASE_NUMERIC_FEATURES + extra_features) if f in train.columns]
    cat_idx = [use_features.index(c) for c in CATEGORICAL_FEATURES if c in use_features]

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
    out["chosen_side"] = np.where(choose_mom, "MOM", "REV")
    out["chosen_pnl_bps"] = np.where(choose_mom, out["pnl_bps"], -out["pnl_bps"])
    out["edge_score"] = out["pred_pnl"]
    return out, use_features


def _threshold_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int]] = []
    for t in EDGE_THRESHOLDS:
        sub = df[df["edge_score"] > t]
        pnl = sub["chosen_pnl_bps"].to_numpy()
        for cost in COSTS_BPS:
            net = pnl - cost if len(pnl) else pnl
            rows.append(
                {
                    "edge_threshold": t,
                    "cost_bps": cost,
                    "trades": int(len(sub)),
                    "rev_share_pct": float((sub["chosen_side"] == "REV").mean() * 100.0) if len(sub) else 0.0,
                    "gross_win_rate_pct": float((pnl > 0).mean() * 100.0) if len(pnl) else 0.0,
                    "gross_mean_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                    "gross_total_pnl_bps": float(pnl.sum()) if len(pnl) else 0.0,
                    "net_win_rate_pct": float((net > 0).mean() * 100.0) if len(net) else 0.0,
                    "net_mean_pnl_bps": float(net.mean()) if len(net) else 0.0,
                    "net_total_pnl_bps": float(net.sum()) if len(net) else 0.0,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bar", choices=DATA_PATHS.keys(), default="m5")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    data_path = DATA_PATHS[args.bar]
    df = pl.read_csv(data_path).to_pandas()

    mom = df[df["strategy_type"] == "MOM"].copy()
    train = mom[mom["year"] <= 2023].copy()
    test = mom[mom["year"] >= 2024].copy()

    holdout_pred, features = _fit_two_stage(train, test)
    holdout_rows = _threshold_rows(holdout_pred)
    out_path = os.path.join(OUT_DIR, f"{args.bar}_two_stage_holdout_thresholds_usfeat.csv")
    holdout_rows.to_csv(out_path, index=False)

    view = holdout_rows[
        (holdout_rows["cost_bps"] == 5) & (holdout_rows["edge_threshold"].isin([4, 5]))
    ][
        [
            "edge_threshold",
            "trades",
            "rev_share_pct",
            "gross_win_rate_pct",
            "gross_mean_pnl_bps",
            "net_win_rate_pct",
            "net_mean_pnl_bps",
            "net_total_pnl_bps",
        ]
    ]
    print(f"\n{args.bar.upper()} US-feature two-stage holdout summary (cost=5bps):")
    print(view.to_string(index=False))
    print(f"\nSaved:\n- {out_path}")
    print(f"Used {len(features)} features.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Two-stage dual-model exploration:
- Train MOM model on MOM rows
- Train REV model on REV rows
For each signal (MOM row), compute edge_mom and edge_rev from respective models.
Select side with higher edge; trade only if max_edge > threshold.

Outputs (per bar size):
- data/analysis/<bar>_dual_models_holdout_thresholds.csv
- data/analysis/<bar>_dual_models_wfo_thresholds.csv
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


def _predict_edges(
    mom_df: pd.DataFrame,
    clf_mom: CatBoostClassifier,
    reg_mom: CatBoostRegressor,
    clf_rev: CatBoostClassifier,
    reg_rev: CatBoostRegressor,
    use_features: list[str],
) -> pd.DataFrame:
    out = mom_df.copy()

    out["p_mom"] = clf_mom.predict_proba(out[use_features])[:, 1]
    out["pred_pnl_mom"] = reg_mom.predict(out[use_features])
    out["edge_mom"] = out["pred_pnl_mom"]

    out["p_rev"] = clf_rev.predict_proba(out[use_features])[:, 1]
    out["pred_pnl_rev"] = reg_rev.predict(out[use_features])
    out["edge_rev"] = out["pred_pnl_rev"]

    choose_rev = out["edge_rev"] > out["edge_mom"]
    out["chosen_side"] = np.where(choose_rev, "REV", "MOM")
    # REV pnl is negative of MOM pnl for matched signals
    out["chosen_pnl_bps"] = np.where(choose_rev, -out["pnl_bps"], out["pnl_bps"])
    out["edge_score"] = np.where(choose_rev, out["edge_rev"], out["edge_mom"])
    return out


def _threshold_rows(df: pd.DataFrame, with_year: bool = False) -> pd.DataFrame:
    rows: list[dict[str, float | int]] = []
    for t in EDGE_THRESHOLDS:
        sub = df[df["edge_score"] > t]
        pnl = sub["chosen_pnl_bps"].to_numpy()
        for cost in COSTS_BPS:
            net = pnl - cost if len(pnl) else pnl
            row = {
                "edge_threshold": t,
                "cost_bps": cost,
                "trades": len(sub),
                "rev_share_pct": float((sub["chosen_side"] == "REV").mean() * 100.0) if len(sub) else 0.0,
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
    parser.add_argument("--bar", choices=["m5", "m15"], default="m5")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    df = pl.read_csv(DATA_PATHS[args.bar]).to_pandas()
    mom = df[df["strategy_type"] == "MOM"].copy()
    rev = df[df["strategy_type"] == "REV"].copy()

    train_mom = mom[mom["year"] <= 2023].copy()
    test_mom = mom[mom["year"] >= 2024].copy()
    train_rev = rev[rev["year"] <= 2023].copy()
    test_rev = rev[rev["year"] >= 2024].copy()

    clf_mom, reg_mom, use_features = _fit_models(train_mom, test_mom)
    clf_rev, reg_rev, _ = _fit_models(train_rev, test_rev)

    holdout_pred = _predict_edges(test_mom, clf_mom, reg_mom, clf_rev, reg_rev, use_features)
    holdout_rows = _threshold_rows(holdout_pred)
    holdout_out = os.path.join(OUT_DIR, f"{args.bar}_dual_models_holdout_thresholds.csv")
    holdout_rows.to_csv(holdout_out, index=False)

    # WFO
    wfo_frames = []
    for year in [2022, 2023, 2024, 2025]:
        tr_m = mom[mom["year"] < year].copy()
        te_m = mom[mom["year"] == year].copy()
        tr_r = rev[rev["year"] < year].copy()
        te_r = rev[rev["year"] == year].copy()
        if len(tr_m) < 10000 or len(te_m) < 1000:
            continue
        clf_m, reg_m, use_features = _fit_models(tr_m, te_m)
        clf_r, reg_r, _ = _fit_models(tr_r, te_r)
        pred = _predict_edges(te_m, clf_m, reg_m, clf_r, reg_r, use_features)
        rows = _threshold_rows(pred, with_year=True)
        rows["test_year"] = year
        wfo_frames.append(rows)

    wfo_df = pd.concat(wfo_frames, ignore_index=True) if wfo_frames else pd.DataFrame()
    wfo_out = os.path.join(OUT_DIR, f"{args.bar}_dual_models_wfo_thresholds.csv")
    wfo_df.to_csv(wfo_out, index=False)

    view = holdout_rows[(holdout_rows["cost_bps"] == 5) & (holdout_rows["edge_threshold"].isin([4, 5]))][
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
    print(f"\n{args.bar.upper()} dual-model holdout (cost=5bps):")
    print(view.to_string(index=False))
    print(f"\nSaved:\n- {holdout_out}\n- {wfo_out}")


if __name__ == "__main__":
    main()

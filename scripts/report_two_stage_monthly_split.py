#!/usr/bin/env python3
"""
Monthly breakdown for split-threshold two-stage model.
Selects separate MOM/REV thresholds on train (<=2023) and applies to holdout (2024-2025).
Outputs:
- data/analysis/<bar>_two_stage_monthly_split_selected.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier, CatBoostRegressor, Pool

DATA_PATHS = {
    "m5": "data/meta_model/events_m5_8yr_v3_dual.csv",
    "m15": "data/meta_model/events_m15_8yr_v3_dual.csv",
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
    "atr_ratio",
    "entry_atr",
    "vol_regime",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

EDGE_THRESHOLDS = [0, 1, 2, 3, 4, 5, 7, 10]
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
    choose_mom = out["p_up"] >= 0.5
    out["chosen_side"] = np.where(choose_mom, "MOM", "REV")
    out["chosen_pnl_bps"] = np.where(choose_mom, out["pnl_bps"], -out["pnl_bps"])
    out["edge_score"] = out["pred_pnl"]
    return out


def _select_split_thresholds(train_pred: pd.DataFrame, cost: int = 5) -> tuple[int, int]:
    best = {}
    for side in ["MOM", "REV"]:
        side_df = train_pred[train_pred["chosen_side"] == side]
        best_t = EDGE_THRESHOLDS[0]
        best_net = -np.inf
        for t in EDGE_THRESHOLDS:
            sub = side_df[np.abs(side_df["edge_score"]) > t]
            pnl = sub["chosen_pnl_bps"].to_numpy()
            net_total = float((pnl - cost).sum()) if len(pnl) else 0.0
            if net_total > best_net:
                best_net = net_total
                best_t = t
        best[side] = best_t
    return best["MOM"], best["REV"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bar", choices=["m5", "m15"], default="m5")
    args = parser.parse_args()

    data_path = DATA_PATHS[args.bar]
    out_path = Path(f"data/analysis/{args.bar}_two_stage_monthly_split_selected.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = pl.read_csv(data_path).to_pandas()
    mom = df[df["strategy_type"] == "MOM"].copy()
    train = mom[mom["year"] <= 2023].copy()
    test = mom[mom["year"] >= 2024].copy()

    clf, reg_abs, use_features = _fit_models(train, test)
    train_pred = _predict(train, clf, reg_abs, use_features)
    test_pred = _predict(test, clf, reg_abs, use_features)

    t_mom, t_rev = _select_split_thresholds(train_pred, cost=COST_BPS)
    mask = ((test_pred["chosen_side"] == "MOM") & (np.abs(test_pred["edge_score"]) > t_mom)) | (
        (test_pred["chosen_side"] == "REV") & (np.abs(test_pred["edge_score"]) > t_rev)
    )
    filt = test_pred[mask].copy()

    filt["timestamp"] = pd.to_datetime(filt["timestamp"], errors="coerce")
    filt = filt.dropna(subset=["timestamp"])
    filt["month"] = filt["timestamp"].dt.strftime("%Y-%m")

    rows = []
    for month, sub in filt.groupby("month"):
        pnl = sub["chosen_pnl_bps"].to_numpy()
        if len(pnl):
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
                "trades": len(pnl),
                "gross_win_rate_pct": gross_wr,
                "gross_mean_pnl_bps": gross_mean,
                "gross_total_pnl_bps": gross_total,
                "net_win_rate_pct": net_wr,
                "net_mean_pnl_bps": net_mean,
                "net_total_pnl_bps": net_total,
                "t_mom": t_mom,
                "t_rev": t_rev,
            }
        )

    out = pd.DataFrame(rows).sort_values("month")
    out.to_csv(out_path, index=False)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()

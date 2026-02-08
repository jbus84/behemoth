#!/usr/bin/env python3
"""
H1 Meta Model Two-Stage Training (MOM-only)
- Stage 1: classifier for MOM win probability
- Stage 2: regressor for expected signed PnL
Edge = pred_pnl (expected value)
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier, CatBoostRegressor, Pool

DATA_PATH = "data/meta_model/events_h1_8yr_v3_dual.csv"
MODEL_DIR = "models/meta_model_h1"
ANALYSIS_DIR = "data/analysis"

CATEGORICAL_FEATURES = ["active_leg", "side"]
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


def _predict(
    df: pd.DataFrame, clf: CatBoostClassifier, reg_pnl: CatBoostRegressor, use_features: list[str]
) -> pd.DataFrame:
    out = df.copy()
    out["p_up"] = clf.predict_proba(out[use_features])[:, 1]
    out["pred_pnl"] = reg_pnl.predict(out[use_features])
    out["chosen_side"] = np.where(out["p_up"] >= 0.5, "MOM", "REV")
    out["chosen_pnl_bps"] = np.where(out["p_up"] >= 0.5, out["pnl_bps"], -out["pnl_bps"])
    out["edge_score"] = out["pred_pnl"]
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
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(ANALYSIS_DIR, exist_ok=True)

    df = pl.read_csv(DATA_PATH).to_pandas()
    mom = df[df["strategy_type"] == "MOM"].copy()

    train = mom[mom["year"] <= 2023].copy()
    test = mom[mom["year"] >= 2024].copy()

    clf, reg_pnl, use_features = _fit_models(train, test)

    # Save models
    clf_path = os.path.join(MODEL_DIR, "catboost_h1_clf.cbm")
    reg_path = os.path.join(MODEL_DIR, "catboost_h1_reg.cbm")
    clf.save_model(clf_path)
    reg_pnl.save_model(reg_path)

    # Holdout metrics
    holdout_pred = _predict(test, clf, reg_pnl, use_features)
    holdout_rows = _threshold_rows(holdout_pred)
    holdout_out = os.path.join(ANALYSIS_DIR, "h1_two_stage_holdout_thresholds_mom_only.csv")
    holdout_rows.to_csv(holdout_out, index=False)

    # WFO
    wfo_frames = []
    for year in [2022, 2023, 2024, 2025]:
        tr = mom[mom["year"] < year].copy()
        te = mom[mom["year"] == year].copy()
        if len(tr) < 1000 or len(te) < 100:
            continue
        clf_y, reg_y, feat_y = _fit_models(tr, te)
        pred = _predict(te, clf_y, reg_y, feat_y)
        rows = _threshold_rows(pred, with_year=True)
        rows["test_year"] = year
        wfo_frames.append(rows)

    wfo_df = pd.concat(wfo_frames, ignore_index=True) if wfo_frames else pd.DataFrame()
    wfo_out = os.path.join(ANALYSIS_DIR, "h1_two_stage_wfo_thresholds_mom_only.csv")
    wfo_df.to_csv(wfo_out, index=False)

    view = holdout_rows[(holdout_rows["cost_bps"] == 5) & (holdout_rows["edge_threshold"].isin([4, 5]))]
    print("\nH1 two-stage holdout (cost=5bps, MOM-only):")
    print(view.to_string(index=False))
    print("\nSaved:")
    print(f"- {clf_path}")
    print(f"- {reg_path}")
    print(f"- {holdout_out}")
    print(f"- {wfo_out}")


if __name__ == "__main__":
    main()

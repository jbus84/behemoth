#!/usr/bin/env python3
"""
Evaluate whether SPX pairs should use a separate model.

Compares:
1) Baseline pooled model (saved production model)
2) SPX overlay model (SPX-only model replaces SPX predictions)
3) Full split models (SPX-only + non-SPX-only models)

All metrics use the existing holdout protocol:
- Event-level best MOM/REV per (pair, timestamp)
- Holdout years >= 2024
- Trade filter: pred_pnl > 20
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostRegressor, Pool

DATA_PATH = "data/analysis/mfe_mae_h1.csv"
MODEL_PATH = "models/meta_model_h1/catboost_h1_reg.cbm"
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

MODEL_PARAMS = dict(
    iterations=1000,
    depth=6,
    learning_rate=0.03,
    loss_function="RMSE",
    verbose=False,
    random_seed=42,
)


@dataclass
class EvalResult:
    scenario: str
    trades: int
    win_rate: float
    mean_pnl: float
    total_pnl: float
    max_dd: float
    spx_trades: int
    non_spx_trades: int
    spx_total_pnl: float
    non_spx_total_pnl: float


def max_drawdown(pnl: np.ndarray) -> float:
    if len(pnl) == 0:
        return 0.0
    curve = np.cumsum(pnl)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def fit_model(df_train: pd.DataFrame, df_eval: pd.DataFrame, features: list[str]) -> CatBoostRegressor:
    cat_indices = [df_train[features].columns.get_loc(c) for c in CATEGORICAL_FEATURES if c in features]
    model = CatBoostRegressor(**MODEL_PARAMS)
    model.fit(
        Pool(df_train[features], df_train["pnl_bps"], cat_features=cat_indices),
        eval_set=Pool(df_eval[features], df_eval["pnl_bps"], cat_features=cat_indices),
        early_stopping_rounds=50,
    )
    return model


def select_trades(df: pd.DataFrame, threshold: float = 20.0) -> pd.DataFrame:
    idx = df.groupby(["pair", "timestamp"])["pred_pnl"].idxmax()
    best = df.loc[idx].copy()
    selected = best[(best["year"] >= 2024) & (best["pred_pnl"] > threshold)].copy()
    selected["is_spx"] = selected["pair"].str.startswith("SPX/")
    return selected.sort_values("timestamp")


def evaluate(df: pd.DataFrame, scenario: str) -> EvalResult:
    selected = select_trades(df, threshold=20.0)
    pnl = selected["pnl_bps"].to_numpy()
    spx = selected[selected["is_spx"]]
    non = selected[~selected["is_spx"]]
    return EvalResult(
        scenario=scenario,
        trades=len(selected),
        win_rate=float((pnl > 0).mean() * 100.0) if len(pnl) else 0.0,
        mean_pnl=float(pnl.mean()) if len(pnl) else 0.0,
        total_pnl=float(pnl.sum()) if len(pnl) else 0.0,
        max_dd=max_drawdown(pnl),
        spx_trades=len(spx),
        non_spx_trades=len(non),
        spx_total_pnl=float(spx["pnl_bps"].sum()) if len(spx) else 0.0,
        non_spx_total_pnl=float(non["pnl_bps"].sum()) if len(non) else 0.0,
    )


def threshold_sweep(df_pred: pd.DataFrame) -> pd.DataFrame:
    idx = df_pred.groupby(["pair", "timestamp"])["pred_pnl"].idxmax()
    best = df_pred.loc[idx].copy()
    best = best[best["year"] >= 2024].copy()
    best["is_spx"] = best["pair"].str.startswith("SPX/")
    rows = []
    for spx_thr in [20, 25, 30, 35, 40, 50, 60]:
        sel = best[
            ((best["is_spx"]) & (best["pred_pnl"] > spx_thr))
            | ((~best["is_spx"]) & (best["pred_pnl"] > 20))
        ].sort_values("timestamp")
        pnl = sel["pnl_bps"].to_numpy()
        rows.append(
            {
                "spx_threshold": spx_thr,
                "trades": len(sel),
                "win_rate": float((pnl > 0).mean() * 100.0) if len(pnl) else 0.0,
                "mean_pnl": float(pnl.mean()) if len(pnl) else 0.0,
                "total_pnl": float(pnl.sum()) if len(pnl) else 0.0,
                "max_dd": max_drawdown(pnl),
                "spx_trades": int(sel["is_spx"].sum()) if len(sel) else 0,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pl.read_csv(DATA_PATH).to_pandas()
    train = df[df["year"] <= 2023].copy()
    test = df[df["year"] >= 2024].copy()

    baseline_model = CatBoostRegressor()
    baseline_model.load_model(MODEL_PATH)

    baseline_pred = df.copy()
    use_features = [f for f in ALL_FEATURES if f in df.columns]
    baseline_pred["pred_pnl"] = baseline_model.predict(baseline_pred[use_features])

    train_spx = train[train["pair"].str.startswith("SPX/")]
    test_spx = test[test["pair"].str.startswith("SPX/")]
    train_non = train[~train["pair"].str.startswith("SPX/")]
    test_non = test[~test["pair"].str.startswith("SPX/")]

    spx_model = fit_model(train_spx, test_spx, use_features)
    non_model = fit_model(train_non, test_non, use_features)

    overlay_pred = baseline_pred.copy()
    mask_spx = overlay_pred["pair"].str.startswith("SPX/")
    overlay_pred.loc[mask_spx, "pred_pnl"] = spx_model.predict(overlay_pred.loc[mask_spx, use_features])

    split_pred = df.copy()
    split_mask_spx = split_pred["pair"].str.startswith("SPX/")
    split_pred.loc[split_mask_spx, "pred_pnl"] = spx_model.predict(split_pred.loc[split_mask_spx, use_features])
    split_pred.loc[~split_mask_spx, "pred_pnl"] = non_model.predict(split_pred.loc[~split_mask_spx, use_features])

    results = [
        evaluate(baseline_pred, "baseline_saved_model"),
        evaluate(overlay_pred, "spx_overlay"),
        evaluate(split_pred, "full_split"),
    ]
    results_df = pd.DataFrame([r.__dict__ for r in results])
    out_results = os.path.join(OUT_DIR, "spx_model_split_results.csv")
    results_df.to_csv(out_results, index=False)

    sweep_df = threshold_sweep(baseline_pred)
    out_sweep = os.path.join(OUT_DIR, "spx_threshold_sweep.csv")
    sweep_df.to_csv(out_sweep, index=False)

    print("\nSPX model split comparison:")
    print(results_df.to_string(index=False))
    print(f"\nSaved: {out_results}")

    print("\nBaseline model with SPX threshold sweep (non-SPX fixed at >20):")
    print(sweep_df.to_string(index=False))
    print(f"\nSaved: {out_sweep}")


if __name__ == "__main__":
    main()

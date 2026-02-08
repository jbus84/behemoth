#!/usr/bin/env python3
"""
Extended validation for M15 MOM quantile models:
1) Coverage by year
2) Coverage by pair
3) Conditional coverage (reliability) by prediction bins
4) Baseline pinball loss comparison
5) Rolling holdouts

Outputs:
 - data/analysis/m15_mom_quantile_validation_year.csv
 - data/analysis/m15_mom_quantile_validation_pair.csv
 - data/analysis/m15_mom_quantile_validation_bins.csv
 - data/analysis/m15_mom_quantile_validation_baseline.csv
 - data/analysis/m15_mom_quantile_validation_rolling.csv
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

DATA_PATH = "data/analysis/m15_mom_quantile_dataset.csv"
MODEL_DIR = "models/m15_mom_quantile"
OUT_DIR = "data/analysis"

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
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

TARGETS = [
    "mfe_bps",
    "mae_bps",
    "mfe_bps_hedged",
    "mae_bps_hedged",
]
QUANTILES = [0.4, 0.6]


def _pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, q: float) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.maximum(q * diff, (q - 1.0) * diff)))


def _load_preds(df: pd.DataFrame) -> dict[str, dict[float, np.ndarray]]:
    X = df[[f for f in ALL_FEATURES if f in df.columns]]
    preds: dict[str, dict[float, np.ndarray]] = {}
    for target in TARGETS:
        preds[target] = {}
        for q in QUANTILES:
            name = f"{target.replace('_bps','')}_q{int(q*100)}.cbm"
            path = os.path.join(MODEL_DIR, name)
            model = CatBoostRegressor()
            model.load_model(path)
            preds[target][q] = model.predict(X)
    return preds


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ns", utc=True, errors="coerce")
    df["year"] = df["timestamp"].dt.year

    test = df[df["year"] >= 2024].copy()
    test = test.reset_index(drop=True)
    preds = _load_preds(test)

    # 1) Coverage by year
    year_rows = []
    for year, sub in test.groupby("year"):
        for target in TARGETS:
            y = sub[target].to_numpy()
            for q in QUANTILES:
                yhat = preds[target][q][sub.index]
                year_rows.append(
                    {
                        "year": int(year),
                        "target": target,
                        "quantile": q,
                        "coverage": float(np.mean(y <= yhat)),
                        "rows": int(len(y)),
                    }
                )
    pd.DataFrame(year_rows).to_csv(os.path.join(OUT_DIR, "m15_mom_quantile_validation_year.csv"), index=False)

    # 2) Coverage by pair (only if enough rows)
    pair_rows = []
    for pair, sub in test.groupby("pair"):
        if len(sub) < 200:
            continue
        for target in TARGETS:
            y = sub[target].to_numpy()
            for q in QUANTILES:
                yhat = preds[target][q][sub.index]
                pair_rows.append(
                    {
                        "pair": pair,
                        "target": target,
                        "quantile": q,
                        "coverage": float(np.mean(y <= yhat)),
                        "rows": int(len(y)),
                    }
                )
    pd.DataFrame(pair_rows).to_csv(os.path.join(OUT_DIR, "m15_mom_quantile_validation_pair.csv"), index=False)

    # 3) Conditional coverage by prediction bins
    bin_rows = []
    for target in TARGETS:
        for q in QUANTILES:
            y = test[target].to_numpy()
            yhat = preds[target][q]
            bins = pd.qcut(yhat, 10, duplicates="drop")
            bin_series = pd.Series(bins)
            for b, idx in bin_series.groupby(bin_series).groups.items():
                yb = y[idx]
                yhb = yhat[idx]
                bin_rows.append(
                    {
                        "target": target,
                        "quantile": q,
                        "bin": str(b),
                        "coverage": float(np.mean(yb <= yhb)),
                        "rows": int(len(idx)),
                        "pred_mean": float(np.mean(yhb)),
                    }
                )
    pd.DataFrame(bin_rows).to_csv(os.path.join(OUT_DIR, "m15_mom_quantile_validation_bins.csv"), index=False)

    # 4) Baseline pinball loss (train quantile constant)
    baseline_rows = []
    train = df[df["year"] <= 2023].copy()
    for target in TARGETS:
        y_train = train[target].to_numpy()
        y_test = test[target].to_numpy()
        for q in QUANTILES:
            baseline = float(np.quantile(y_train, q))
            baseline_loss = _pinball_loss(y_test, np.full_like(y_test, baseline), q)
            model_loss = _pinball_loss(y_test, preds[target][q], q)
            baseline_rows.append(
                {
                    "target": target,
                    "quantile": q,
                    "baseline_quantile": baseline,
                    "baseline_pinball": baseline_loss,
                    "model_pinball": model_loss,
                }
            )
    pd.DataFrame(baseline_rows).to_csv(os.path.join(OUT_DIR, "m15_mom_quantile_validation_baseline.csv"), index=False)

    # 5) Rolling holdouts
    rolling_rows = []
    windows = [
        ("2018-2021", "2022"),
        ("2018-2022", "2023"),
        ("2018-2023", "2024"),
        ("2018-2024", "2025"),
    ]
    for train_years, test_year in windows:
        start, end = train_years.split("-")
        start = int(start)
        end = int(end)
        ty = int(test_year)
        tr = df[(df["year"] >= start) & (df["year"] <= end)]
        te = df[df["year"] == ty]
        if te.empty or tr.empty:
            continue

        X_train = tr[[f for f in ALL_FEATURES if f in df.columns]]
        X_test = te[[f for f in ALL_FEATURES if f in df.columns]]

        for target in TARGETS:
            y_train = tr[target].to_numpy()
            y_test = te[target].to_numpy()
            for q in QUANTILES:
                model = CatBoostRegressor(
                    iterations=1000,
                    depth=7,
                    learning_rate=0.03,
                    random_seed=42,
                    verbose=False,
                    loss_function=f"Quantile:alpha={q}",
                )
                cat_idx = [X_train.columns.get_loc(c) for c in CATEGORICAL_FEATURES if c in X_train.columns]
                model.fit(
                    X_train,
                    y_train,
                    cat_features=cat_idx,
                )
                yhat = model.predict(X_test)
                rolling_rows.append(
                    {
                        "train_years": train_years,
                        "test_year": ty,
                        "target": target,
                        "quantile": q,
                        "pinball_loss": _pinball_loss(y_test, yhat, q),
                        "coverage": float(np.mean(y_test <= yhat)),
                        "rows_test": len(y_test),
                    }
                )
    pd.DataFrame(rolling_rows).to_csv(os.path.join(OUT_DIR, "m15_mom_quantile_validation_rolling.csv"), index=False)

    print("Saved validation outputs to data/analysis.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Train CatBoost quantile models for M15 MOM MFE/MAE targets.
Targets:
 - mfe_bps, mae_bps (active)
 - mfe_bps_hedged, mae_bps_hedged (hedged path)

Quantiles: 0.1 / 0.5 / 0.9

Outputs:
 - models/m15_mom_quantile/*.cbm
 - data/analysis/m15_mom_quantile_fit_metrics.csv
"""

from __future__ import annotations

import os
from typing import Iterable

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

DATA_PATH = "data/analysis/m15_mom_quantile_dataset.csv"
MODEL_DIR = "models/m15_mom_quantile"
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
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

TARGETS = [
    ("mfe_bps", "active"),
    ("mae_bps", "active"),
    ("mfe_bps_hedged", "hedged"),
    ("mae_bps_hedged", "hedged"),
]

QUANTILES = [0.2, 0.4, 0.6]

MODEL_PARAMS = dict(
    iterations=1200,
    depth=7,
    learning_rate=0.03,
    random_seed=42,
    verbose=False,
)


def _pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, q: float) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.maximum(q * diff, (q - 1.0) * diff)))


def _train_one(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    quantile: float,
    cat_features: list[int],
) -> tuple[CatBoostRegressor, dict[str, float]]:
    model = CatBoostRegressor(
        **MODEL_PARAMS,
        loss_function=f"Quantile:alpha={quantile}",
    )
    model.fit(
        Pool(X_train, y_train, cat_features=cat_features),
        eval_set=Pool(X_test, y_test, cat_features=cat_features),
        early_stopping_rounds=80,
    )
    preds = model.predict(X_test)
    metrics = {
        "pinball": _pinball_loss(y_test, preds, quantile),
        "coverage": float(np.mean(y_test <= preds)),
    }
    return model, metrics


def main() -> None:
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(ANALYSIS_DIR, exist_ok=True)

    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ns", utc=True, errors="coerce")
    df["year"] = df["timestamp"].dt.year

    train = df[df["year"] <= 2023].copy()
    test = df[df["year"] >= 2024].copy()

    use_features = [f for f in ALL_FEATURES if f in df.columns]
    cat_idx = [use_features.index(c) for c in CATEGORICAL_FEATURES if c in use_features]

    X_train = train[use_features]
    X_test = test[use_features]

    metrics_rows = []

    for target, tag in TARGETS:
        y_train = train[target].to_numpy()
        y_test = test[target].to_numpy()

        for q in QUANTILES:
            model, metrics = _train_one(X_train, y_train, X_test, y_test, q, cat_idx)
            name = f"{target.replace('_bps','')}_q{int(q*100)}"
            model_path = os.path.join(MODEL_DIR, f"{name}.cbm")
            model.save_model(model_path)

            metrics_rows.append(
                {
                    "target": target,
                    "target_tag": tag,
                    "quantile": q,
                    "model_path": model_path,
                    "pinball_loss": metrics["pinball"],
                    "coverage": metrics["coverage"],
                    "rows_train": len(train),
                    "rows_test": len(test),
                }
            )

    out = pd.DataFrame(metrics_rows)
    out.to_csv(os.path.join(ANALYSIS_DIR, "m15_mom_quantile_fit_metrics.csv"), index=False)
    print("Saved models to:", MODEL_DIR)
    print("Saved metrics: data/analysis/m15_mom_quantile_fit_metrics.csv")


if __name__ == "__main__":
    main()

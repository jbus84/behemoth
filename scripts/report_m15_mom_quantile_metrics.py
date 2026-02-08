#!/usr/bin/env python3
"""
Report quantile ordering and calibration metrics for M15 MOM quantile models.

Outputs:
 - data/analysis/m15_mom_quantile_metrics.csv
 - data/analysis/m15_mom_quantile_ordering.csv
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

QUANTILES = [0.2, 0.4, 0.6]


def _pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, q: float) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.maximum(q * diff, (q - 1.0) * diff)))


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ns", utc=True, errors="coerce")
    df["year"] = df["timestamp"].dt.year
    test = df[df["year"] >= 2024].copy()

    use_features = [f for f in ALL_FEATURES if f in df.columns]
    X_test = test[use_features]

    metrics_rows = []
    ordering_rows = []

    for target in TARGETS:
        preds = {}
        y_true = test[target].to_numpy()

        for q in QUANTILES:
            name = f"{target.replace('_bps','')}_q{int(q*100)}.cbm"
            path = os.path.join(MODEL_DIR, name)
            model = CatBoostRegressor()
            model.load_model(path)
            y_pred = model.predict(X_test)
            preds[q] = y_pred

            metrics_rows.append(
                {
                    "target": target,
                    "quantile": q,
                    "pinball_loss": _pinball_loss(y_true, y_pred, q),
                    "coverage": float(np.mean(y_true <= y_pred)),
                }
            )

        q20 = preds[0.2]
        q40 = preds[0.4]
        q60 = preds[0.6]
        ordering_rows.append(
            {
                "target": target,
                "pct_q20_gt_q40": float(np.mean(q20 > q40) * 100.0),
                "pct_q40_gt_q60": float(np.mean(q40 > q60) * 100.0),
            }
        )

    pd.DataFrame(metrics_rows).to_csv(os.path.join(OUT_DIR, "m15_mom_quantile_metrics.csv"), index=False)
    pd.DataFrame(ordering_rows).to_csv(os.path.join(OUT_DIR, "m15_mom_quantile_ordering.csv"), index=False)
    print("Saved:")
    print("- data/analysis/m15_mom_quantile_metrics.csv")
    print("- data/analysis/m15_mom_quantile_ordering.csv")


if __name__ == "__main__":
    main()

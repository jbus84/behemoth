#!/usr/bin/env python3
"""
Evaluate gating rule on M15 MOM:
enter only if MFE_q60 >= k * |MAE_q40|.

Outputs:
- data/analysis/m15_mom_quantile_gate_summary.csv
- data/analysis/m15_mom_quantile_gate_by_k.csv
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

K_VALUES = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]


def _max_dd(pnl: np.ndarray) -> float:
    if len(pnl) == 0:
        return 0.0
    curve = np.cumsum(pnl)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(pnl: np.ndarray) -> dict:
    if len(pnl) == 0:
        return dict(trades=0, win_rate=0.0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0)
    return dict(
        trades=int(len(pnl)),
        win_rate=float((pnl > 0).mean() * 100.0),
        mean_pnl=float(pnl.mean()),
        total_pnl=float(pnl.sum()),
        max_dd=_max_dd(pnl),
    )


def _load_model(name: str) -> CatBoostRegressor:
    model = CatBoostRegressor()
    model.load_model(os.path.join(MODEL_DIR, name))
    return model


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ns", utc=True, errors="coerce")
    df["year"] = df["timestamp"].dt.year
    test = df[df["year"] >= 2024].copy().reset_index(drop=True)

    use_features = [f for f in ALL_FEATURES if f in df.columns]
    X_test = test[use_features]

    mfe_q40 = _load_model("mfe_q40.cbm").predict(X_test)
    mae_q60 = _load_model("mae_q60.cbm").predict(X_test)

    pnl = test["pnl_bps"].to_numpy()

    rows = []
    for k in K_VALUES:
        mask = mfe_q40 >= k * np.abs(mae_q60)
        stats = _metrics(pnl[mask])
        stats["k"] = k
        stats["pass_rate"] = float(mask.mean() * 100.0)
        rows.append(stats)

    out = pd.DataFrame(rows).sort_values("k")
    out.to_csv(os.path.join(OUT_DIR, "m15_mom_quantile_gate_by_k.csv"), index=False)

    # baseline (no filter)
    base = _metrics(pnl)
    base["k"] = 0.0
    base["pass_rate"] = 100.0
    pd.DataFrame([base]).to_csv(os.path.join(OUT_DIR, "m15_mom_quantile_gate_summary.csv"), index=False)

    print("Saved:")
    print("- data/analysis/m15_mom_quantile_gate_by_k.csv")
    print("- data/analysis/m15_mom_quantile_gate_summary.csv")


if __name__ == "__main__":
    main()

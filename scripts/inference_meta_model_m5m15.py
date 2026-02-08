#!/usr/bin/env python3
"""
M5/M15 inference for MOM-only expected-PnL model.
Uses active-leg features and Kalman Z-score signals; no guardrails enforced.

Outputs:
- data/analysis/inference_m5_latest.csv
- data/analysis/inference_m15_latest.csv
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3_m5 as m5
import build_meta_dataset_v3 as m15


CATEGORICAL_FEATURES = ["strategy_type", "active_leg", "side"]
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
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


def _load_model(path: str) -> CatBoostRegressor:
    model = CatBoostRegressor()
    model.load_model(path)
    return model


def _select_active_leg(beta: float) -> str | None:
    if beta < 0.98:
        return "Y"
    if beta > 1.02:
        return "X"
    return None


def _build_rows(module, min_z: float) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name, fx, fy, cx, cy, cost_y, cost_x in module.PAIRS:
        df = module.load_pair_data(fx, fy, cx, cy)
        if df is None or len(df) < 600:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()

        betas, errors, ret_betas = module.compute_kalman_states(y, x)
        z_scores = module.compute_z_scores(errors)

        i = len(y) - 1
        if i < 500:
            continue

        z = float(z_scores[i])
        if abs(z) < min_z:
            continue

        active_leg = _select_active_leg(float(betas[i]))
        if active_leg is None:
            continue

        features = module.compute_features_at_entry(i, y, x, betas, errors, ret_betas, z_scores, ts)
        side = "LONG" if z >= 0 else "SHORT"

        row = {
            "pair": name,
            "timestamp": ts[i],
            "strategy_type": "MOM",
            "active_leg": active_leg,
            "side": side,
            **features,
        }
        rows.append(row)

    return rows


def _predict(rows: list[dict[str, object]], model: CatBoostRegressor) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    model_features = list(getattr(model, "feature_names_", [])) or ALL_FEATURES

    missing = [f for f in model_features if f not in df.columns]
    for f in missing:
        df[f] = 0.0

    df["pred_pnl"] = model.predict(df[model_features])
    df["edge_score"] = df["pred_pnl"]
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bar", choices=["m5", "m15"], default="m5")
    parser.add_argument("--threshold", type=float, default=4.0)
    parser.add_argument("--min_z", type=float, default=1.5)
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args()

    if args.bar == "m5":
        module = m5
        default_model = "models/meta_model_m5/catboost_m5_reg.cbm"
        out_path = Path("data/analysis/inference_m5_latest.csv")
    else:
        module = m15
        default_model = "models/meta_model_m15/catboost_m15_reg.cbm"
        out_path = Path("data/analysis/inference_m15_latest.csv")

    model_path = args.model or default_model
    model = _load_model(model_path)

    rows = _build_rows(module, args.min_z)
    df = _predict(rows, model)
    if df.empty:
        print("No eligible signals.")
        return

    df["trade"] = df["pred_pnl"] > args.threshold
    df = df.sort_values("pred_pnl", ascending=False)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Saved {out_path} (rows={len(df)})")


if __name__ == "__main__":
    main()

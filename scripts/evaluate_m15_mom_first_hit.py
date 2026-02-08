#!/usr/bin/env python3
"""
Evaluate first-hit ordering using predicted quantile TP/SL:
TP = MFE_q60, SL = |MAE_q40| (active-leg).
Reports which threshold is hit first along the trade path.

Outputs:
- data/analysis/m15_mom_first_hit_summary.csv
- data/analysis/m15_mom_first_hit_by_k.csv
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3 as m15

DATA_PATH = "data/analysis/m15_mom_quantile_dataset.csv"
MODEL_DIR = "models/m15_mom_quantile"
OUT_DIR = "data/analysis"

THRESH_MOM = 1.5
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500
HEDGE_CLIP = 10.0

K_VALUES = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]

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


def _exit_hit(direction: int, z: float) -> bool:
    if direction == 1:
        return z < 0 or z > STOP_LEVEL
    return z > 0 or z < -STOP_LEVEL


def _hedge_ratio(active_leg: str, beta: float) -> float:
    if active_leg == "Y":
        ratio = beta
    else:
        ratio = 0.0 if abs(beta) < 1e-6 else 1.0 / beta
    return float(np.clip(ratio, -HEDGE_CLIP, HEDGE_CLIP))


def _load_model(name: str) -> CatBoostRegressor:
    model = CatBoostRegressor()
    model.load_model(os.path.join(MODEL_DIR, name))
    return model


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    # Load dataset for features + predicted thresholds
    df = pd.read_csv(DATA_PATH)
    df["timestamp_ns"] = df["timestamp"].astype("int64")
    df["timestamp"] = pd.to_datetime(df["timestamp_ns"], unit="ns", utc=True, errors="coerce")
    df["year"] = df["timestamp"].dt.year
    test = df[df["year"] >= 2024].copy().reset_index(drop=True)

    use_features = [f for f in ALL_FEATURES if f in test.columns]
    X_test = test[use_features]

    mfe_q20 = _load_model("mfe_q20.cbm").predict(X_test)
    mae_q60 = _load_model("mae_q60.cbm").predict(X_test)
    mfe_q20_h = _load_model("mfe_hedged_q20.cbm").predict(X_test)
    mae_q60_h = _load_model("mae_hedged_q60.cbm").predict(X_test)

    # Build fast lookup for predictions by trade key
    test["mfe_q20"] = mfe_q20
    test["mae_q60"] = mae_q60
    test["mfe_q20_h"] = mfe_q20_h
    test["mae_q60_h"] = mae_q60_h

    key_cols = ["pair", "timestamp_ns", "side", "active_leg"]
    preds = test.set_index(key_cols)[["mfe_q20", "mae_q60", "mfe_q20_h", "mae_q60_h"]]

    rows = []
    totals = {k: {"tp": 0, "sl": 0, "none": 0} for k in K_VALUES}
    totals_h = {k: {"tp": 0, "sl": 0, "none": 0} for k in K_VALUES}
    pnl_rows = []
    pnl_rows_h = []

    # Iterate trades from raw price series to determine first hit
    for name, fx, fy, cx, cy, _, _ in m15.PAIRS:
        dfp = m15.load_pair_data(fx, fy, cx, cy)
        if dfp is None:
            continue

        y = np.log(dfp["Y"].to_numpy())
        x = np.log(dfp["X"].to_numpy())
        ts = dfp["timestamp"].to_numpy()

        betas, errors, _ = m15.compute_kalman_states(y, x)
        z_scores = m15.compute_z_scores(errors)

        last_entry = 0
        for i in range(500, len(y) - 2):
            z = z_scores[i]
            if abs(z) < THRESH_MOM or i - last_entry < MIN_GAP:
                continue

            beta = betas[i]
            if beta < 0.98:
                active_leg = "Y"
            elif beta > 1.02:
                active_leg = "X"
            else:
                continue

            direction = 1 if z > 0 else -1
            side = "LONG" if direction == 1 else "SHORT"
            key = (name, int(ts[i]), side, active_leg)

            if key not in preds.index:
                last_entry = i
                continue

            entry_pred = preds.loc[key]
            tp_base = float(entry_pred["mfe_q20"])
            sl_base = abs(float(entry_pred["mae_q60"]))
            tp_base_h = float(entry_pred["mfe_q20_h"])
            sl_base_h = abs(float(entry_pred["mae_q60_h"]))

            active = y if active_leg == "Y" else x

            end = min(i + MAX_HOLD, len(z_scores) - 1)
            exit_idx = end

            # Precompute PnL path (active)
            pnl_path = direction * np.diff(active[i : end + 1]) * 10000.0
            curve = np.cumsum(pnl_path)

            # Precompute hedged PnL path
            other = x if active_leg == "Y" else y
            d_active = np.diff(active[i : end + 1])
            d_other = np.diff(other[i : end + 1])
            hedge_ratio = np.array([_hedge_ratio(active_leg, b) for b in betas[i + 1 : end + 1]], dtype=float)
            pnl_path_h = direction * (d_active - hedge_ratio * d_other) * 10000.0
            curve_h = np.cumsum(pnl_path_h)

            for k in K_VALUES:
                # Gate entries by ratio
                if tp_base < k * sl_base:
                    continue
                tp = tp_base * k
                sl = sl_base * k
                tp_h = tp_base_h * k
                sl_h = sl_base_h * k
                hit = "none"
                hit_h = "none"
                pnl_hit = 0.0
                pnl_hit_h = 0.0
                for val in curve:
                    if val >= tp:
                        hit = "tp"
                        pnl_hit = val
                        break
                    if val <= -sl:
                        hit = "sl"
                        pnl_hit = val
                        break

                totals[k][hit] += 1
                pnl_rows.append(
                    {"k": k, "hit": hit, "pnl": pnl_hit, "timestamp": int(ts[i])}
                )

                if tp_base_h < k * sl_base_h:
                    continue

                for val in curve_h:
                    if val >= tp_h:
                        hit_h = "tp"
                        pnl_hit_h = val
                        break
                    if val <= -sl_h:
                        hit_h = "sl"
                        pnl_hit_h = val
                        break

                totals_h[k][hit_h] += 1
                pnl_rows_h.append(
                    {"k": k, "hit": hit_h, "pnl": pnl_hit_h, "timestamp": int(ts[i])}
                )

            # stop when signal exits
            for j in range(i + 1, end + 1):
                if _exit_hit(direction, z_scores[j]):
                    exit_idx = j
                    break

            last_entry = i

    # Summaries
    for k in K_VALUES:
        tot = sum(totals[k].values())
        rows.append(
            {
                "k": k,
                "variant": "active",
                "trades": tot,
                "tp_first": totals[k]["tp"],
                "sl_first": totals[k]["sl"],
                "none": totals[k]["none"],
                "tp_rate": totals[k]["tp"] / tot if tot else 0.0,
                "sl_rate": totals[k]["sl"] / tot if tot else 0.0,
            }
        )

    for k in K_VALUES:
        tot = sum(totals_h[k].values())
        rows.append(
            {
                "k": k,
                "variant": "hedged",
                "trades": tot,
                "tp_first": totals_h[k]["tp"],
                "sl_first": totals_h[k]["sl"],
                "none": totals_h[k]["none"],
                "tp_rate": totals_h[k]["tp"] / tot if tot else 0.0,
                "sl_rate": totals_h[k]["sl"] / tot if tot else 0.0,
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "m15_mom_first_hit_by_k.csv"), index=False)
    out.to_csv(os.path.join(OUT_DIR, "m15_mom_first_hit_summary.csv"), index=False)

    # Realized PnL at first hit
    pnl_df = pd.DataFrame(pnl_rows)
    pnl_df_h = pd.DataFrame(pnl_rows_h)
    pnl_df.to_csv(os.path.join(OUT_DIR, "m15_mom_first_hit_pnl_active.csv"), index=False)
    pnl_df_h.to_csv(os.path.join(OUT_DIR, "m15_mom_first_hit_pnl_hedged.csv"), index=False)
    print("Saved:")
    print("- data/analysis/m15_mom_first_hit_by_k.csv")
    print("- data/analysis/m15_mom_first_hit_summary.csv")


if __name__ == "__main__":
    main()

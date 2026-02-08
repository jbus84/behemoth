#!/usr/bin/env python3
"""
Delayed entry strategy:
- Signal at MOM entry time t0.
- Wait for adverse move to MAE threshold (entry trigger).
- Enter at MAE level and exit at MFE level (relative to original t0).

Uses quantile model predictions for MFE/MAE.

Outputs:
- data/analysis/m15_mom_delayed_entry_summary.csv
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3 as m15

DATA_PATH = "data/analysis/m15_mom_quantile_dataset.csv"
MODEL_DIR = "models/m15_mom_quantile"
OUT_DIR = "data/analysis"

THRESH_MOM = 1.5
MIN_GAP = 20
MAX_HOLD = 500

Q_VALUES = [20, 40, 60]
K_VALUES = [1.0]

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


def _load_model(name: str) -> CatBoostRegressor:
    model = CatBoostRegressor()
    model.load_model(os.path.join(MODEL_DIR, name))
    return model


def _max_dd(pnls: list[tuple[int, float]]) -> float:
    if not pnls:
        return 0.0
    df = pd.DataFrame(pnls, columns=["timestamp", "pnl"]).sort_values("timestamp")
    curve = df["pnl"].cumsum()
    peak = curve.cummax()
    return float((curve - peak).min())


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    df = pd.read_csv(DATA_PATH)
    df["timestamp_ns"] = df["timestamp"].astype("int64")
    df["timestamp"] = pd.to_datetime(df["timestamp_ns"], unit="ns", utc=True, errors="coerce")
    df["year"] = df["timestamp"].dt.year
    test = df[df["year"] >= 2024].copy().reset_index(drop=True)

    use_features = [f for f in ALL_FEATURES if f in test.columns]
    X_test = test[use_features]

    # Precompute predictions
    for q in Q_VALUES:
        test[f"mfe_q{q}"] = _load_model(f"mfe_q{q}.cbm").predict(X_test)
        test[f"mae_q{q}"] = _load_model(f"mae_q{q}.cbm").predict(X_test)

    key_cols = ["pair", "timestamp_ns", "side", "active_leg"]
    preds = test.set_index(key_cols)[
        [f"mfe_q{q}" for q in Q_VALUES] + [f"mae_q{q}" for q in Q_VALUES]
    ]

    # Precompute trade curves once (holdout only)
    trades = []
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

            active = y if active_leg == "Y" else x
            end = min(i + MAX_HOLD, len(z_scores) - 1)
            pnl_path = direction * np.diff(active[i : end + 1]) * 10000.0
            curve = np.cumsum(pnl_path)

            trades.append(
                {
                    "key": key,
                    "timestamp": int(ts[i]),
                    "curve": curve,
                }
            )
            last_entry = i

    # Collect results
    rows = []
    for mfe_q in Q_VALUES:
        for mae_q in Q_VALUES:
            for k in K_VALUES:
                trade_pnls = []
                entries = 0
                wins = 0

                for tr in trades:
                    entry_pred = preds.loc[tr["key"]]
                    mfe = float(entry_pred[f"mfe_q{mfe_q}"]) * k
                    mae = abs(float(entry_pred[f"mae_q{mae_q}"])) * k

                    curve = tr["curve"]
                    mask_entry = curve <= -mae
                    if not mask_entry.any():
                        continue
                    entry_idx = int(np.argmax(mask_entry))
                    entries += 1
                    pnl_entry = curve[entry_idx]

                    mask_exit = curve[entry_idx + 1 :] >= mfe
                    if mask_exit.any():
                        exit_idx = entry_idx + 1 + int(np.argmax(mask_exit))
                        pnl_exit = curve[exit_idx]
                        wins += 1
                    else:
                        pnl_exit = curve[-1]

                    trade_pnls.append((tr["timestamp"], float(pnl_exit - pnl_entry)))

                pnl_vals = [p for _, p in trade_pnls]
                rows.append(
                    {
                        "mfe_q": mfe_q,
                        "mae_q": mae_q,
                        "k": k,
                        "entries": entries,
                        "win_rate": (wins / entries * 100.0) if entries else 0.0,
                        "mean_pnl": float(np.mean(pnl_vals)) if pnl_vals else 0.0,
                        "total_pnl": float(np.sum(pnl_vals)) if pnl_vals else 0.0,
                        "max_dd": _max_dd(trade_pnls),
                    }
                )

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "m15_mom_delayed_entry_summary.csv"), index=False)
    print("Saved: data/analysis/m15_mom_delayed_entry_summary.csv")


if __name__ == "__main__":
    main()

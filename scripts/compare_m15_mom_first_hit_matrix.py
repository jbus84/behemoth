#!/usr/bin/env python3
"""
Evaluate all MFE/MAE quantile combinations (20/40/60) for MOM first-hit.
TP = MFE_qX, SL = |MAE_qY| with entry gate TP >= k * SL.
Active-leg path only.

Outputs:
- data/analysis/m15_mom_first_hit_combo_summary.csv
- data/analysis/m15_mom_first_hit_combo_pnl.csv
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
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500

K_VALUES = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
Q_VALUES = [20, 40, 60]

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


def _load_model(name: str) -> CatBoostRegressor:
    model = CatBoostRegressor()
    model.load_model(os.path.join(MODEL_DIR, name))
    return model


def _max_dd(ts_pnl: list[tuple[int, float]]) -> float:
    if not ts_pnl:
        return 0.0
    df = pd.DataFrame(ts_pnl, columns=["timestamp", "pnl"]).sort_values("timestamp")
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

    # Precompute predictions for all quantiles
    for q in Q_VALUES:
        test[f"mfe_q{q}"] = _load_model(f"mfe_q{q}.cbm").predict(X_test)
        test[f"mae_q{q}"] = _load_model(f"mae_q{q}.cbm").predict(X_test)

    key_cols = ["pair", "timestamp_ns", "side", "active_leg"]
    preds = test.set_index(key_cols)[
        [f"mfe_q{q}" for q in Q_VALUES] + [f"mae_q{q}" for q in Q_VALUES]
    ]

    counts = defaultdict(lambda: {"tp": 0, "sl": 0, "none": 0})
    pnl_store = defaultdict(list)  # key: (mfe_q, mae_q, k)
    hit_store = defaultdict(list)  # key: (mfe_q, mae_q, k) -> list of (timestamp, hit)

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

            active = y if active_leg == "Y" else x
            end = min(i + MAX_HOLD, len(z_scores) - 1)
            pnl_path = direction * np.diff(active[i : end + 1]) * 10000.0
            curve = np.cumsum(pnl_path)

            for mfe_q in Q_VALUES:
                tp0 = float(entry_pred[f"mfe_q{mfe_q}"])
                for mae_q in Q_VALUES:
                    sl0 = abs(float(entry_pred[f"mae_q{mae_q}"]))
                    for k in K_VALUES:
                        if tp0 < k * sl0:
                            continue
                        tp = tp0 * k
                        sl = sl0 * k
                        hit = "none"
                        pnl_hit = 0.0
                        for val in curve:
                            if val >= tp:
                                hit = "tp"
                                pnl_hit = val
                                break
                            if val <= -sl:
                                hit = "sl"
                                pnl_hit = val
                                break
                        counts[(mfe_q, mae_q, k)][
                            "tp" if hit == "tp" else "sl" if hit == "sl" else "none"
                        ] += 1
                        pnl_store[(mfe_q, mae_q, k)].append((int(ts[i]), pnl_hit))
                        hit_store[(mfe_q, mae_q, k)].append((int(ts[i]), hit))

            last_entry = i

    # Summary outputs
    summary_rows = []
    for mfe_q in Q_VALUES:
        for mae_q in Q_VALUES:
            for k in K_VALUES:
                c = counts[(mfe_q, mae_q, k)]
                tot = sum(c.values())
                summary_rows.append(
                    {
                        "mfe_q": mfe_q,
                        "mae_q": mae_q,
                        "k": k,
                        "trades": tot,
                        "tp_first": c["tp"],
                        "sl_first": c["sl"],
                        "none": c["none"],
                        "tp_rate": c["tp"] / tot if tot else 0.0,
                        "sl_rate": c["sl"] / tot if tot else 0.0,
                    }
                )

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(os.path.join(OUT_DIR, "m15_mom_first_hit_combo_summary.csv"), index=False)

    pnl_rows = []
    for mfe_q in Q_VALUES:
        for mae_q in Q_VALUES:
            for k in K_VALUES:
                ts_pnl = pnl_store[(mfe_q, mae_q, k)]
                if not ts_pnl:
                    continue
                pnl = np.array([p for _, p in ts_pnl], dtype=float)
                pnl_rows.append(
                    {
                        "mfe_q": mfe_q,
                        "mae_q": mae_q,
                        "k": k,
                        "trades": len(pnl),
                        "mean_pnl": float(pnl.mean()),
                        "median_pnl": float(np.median(pnl)),
                        "total_pnl": float(pnl.sum()),
                        "win_rate": float((pnl > 0).mean() * 100.0),
                        "max_dd": _max_dd(ts_pnl),
                    }
                )

    pnl_out = pd.DataFrame(pnl_rows)
    pnl_out.to_csv(os.path.join(OUT_DIR, "m15_mom_first_hit_combo_pnl.csv"), index=False)

    # Streak stats
    streak_rows = []
    for mfe_q in Q_VALUES:
        for mae_q in Q_VALUES:
            for k in K_VALUES:
                hits = hit_store[(mfe_q, mae_q, k)]
                if not hits:
                    continue
                dfh = pd.DataFrame(hits, columns=["timestamp", "hit"]).sort_values("timestamp")
                max_tp = 0
                max_sl = 0
                cur_tp = 0
                cur_sl = 0
                for h in dfh["hit"].to_numpy():
                    if h == "tp":
                        cur_tp += 1
                        cur_sl = 0
                        max_tp = max(max_tp, cur_tp)
                    elif h == "sl":
                        cur_sl += 1
                        cur_tp = 0
                        max_sl = max(max_sl, cur_sl)
                    else:
                        cur_tp = 0
                        cur_sl = 0
                streak_rows.append(
                    {
                        "mfe_q": mfe_q,
                        "mae_q": mae_q,
                        "k": k,
                        "trades": len(dfh),
                        "max_tp_streak": max_tp,
                        "max_sl_streak": max_sl,
                    }
                )

    streak_out = pd.DataFrame(streak_rows)
    streak_out.to_csv(os.path.join(OUT_DIR, "m15_mom_first_hit_combo_streaks.csv"), index=False)
    print("Saved:")
    print("- data/analysis/m15_mom_first_hit_combo_summary.csv")
    print("- data/analysis/m15_mom_first_hit_combo_pnl.csv")
    print("- data/analysis/m15_mom_first_hit_combo_streaks.csv")


if __name__ == "__main__":
    main()

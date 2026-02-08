#!/usr/bin/env python3
"""
Compare first-hit TP/SL outcomes across symmetric profiles:
P20/P20, P40/P40, P60/P60 with entry gating.

Outputs:
- data/analysis/m15_mom_first_hit_profiles_summary.csv
- data/analysis/m15_mom_first_hit_profiles_pnl.csv
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
HEDGE_CLIP = 10.0

K_VALUES = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
PROFILES = [20, 40, 60]
MODES = ["normal", "inverted"]

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

    # Precompute predictions for all profiles
    for q in PROFILES:
        test[f"mfe_q{q}"] = _load_model(f"mfe_q{q}.cbm").predict(X_test)
        test[f"mae_q{q}"] = _load_model(f"mae_q{q}.cbm").predict(X_test)
        test[f"mfe_hedged_q{q}"] = _load_model(f"mfe_hedged_q{q}.cbm").predict(X_test)
        test[f"mae_hedged_q{q}"] = _load_model(f"mae_hedged_q{q}.cbm").predict(X_test)

    key_cols = ["pair", "timestamp_ns", "side", "active_leg"]
    preds = test.set_index(key_cols)[
        [f"mfe_q{q}" for q in PROFILES]
        + [f"mae_q{q}" for q in PROFILES]
        + [f"mfe_hedged_q{q}" for q in PROFILES]
        + [f"mae_hedged_q{q}" for q in PROFILES]
    ]

    # Aggregators
    counts = defaultdict(lambda: {"tp": 0, "sl": 0, "none": 0})
    counts_h = defaultdict(lambda: {"tp": 0, "sl": 0, "none": 0})
    pnl_store = defaultdict(list)     # key: (profile, mode, variant, k)
    pnl_store_h = defaultdict(list)   # key: (profile, mode, variant, k)

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
            other = x if active_leg == "Y" else y

            end = min(i + MAX_HOLD, len(z_scores) - 1)
            pnl_path = direction * np.diff(active[i : end + 1]) * 10000.0
            curve = np.cumsum(pnl_path)

            d_active = np.diff(active[i : end + 1])
            d_other = np.diff(other[i : end + 1])
            hedge_ratio = np.array([_hedge_ratio(active_leg, b) for b in betas[i + 1 : end + 1]], dtype=float)
            pnl_path_h = direction * (d_active - hedge_ratio * d_other) * 10000.0
            curve_h = np.cumsum(pnl_path_h)

            for q in PROFILES:
                tp_base = float(entry_pred[f"mfe_q{q}"])
                sl_base = abs(float(entry_pred[f"mae_q{q}"]))
                tp_base_h = float(entry_pred[f"mfe_hedged_q{q}"])
                sl_base_h = abs(float(entry_pred[f"mae_hedged_q{q}"]))

                for mode in MODES:
                    for k in K_VALUES:
                        if mode == "normal":
                            tp0 = tp_base
                            sl0 = sl_base
                            tp0_h = tp_base_h
                            sl0_h = sl_base_h
                            # Gate: require TP >= k * SL
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
                            counts[(q, mode, k)]["tp" if hit == "tp" else "sl" if hit == "sl" else "none"] += 1
                            pnl_store[(q, mode, k)].append((int(ts[i]), pnl_hit))

                            if tp0_h < k * sl0_h:
                                continue
                            tp_h = tp0_h * k
                            sl_h = sl0_h * k
                            hit_h = "none"
                            pnl_hit_h = 0.0
                            for val in curve_h:
                                if val >= tp_h:
                                    hit_h = "tp"
                                    pnl_hit_h = val
                                    break
                                if val <= -sl_h:
                                    hit_h = "sl"
                                    pnl_hit_h = val
                                    break
                            counts_h[(q, mode, k)]["tp" if hit_h == "tp" else "sl" if hit_h == "sl" else "none"] += 1
                            pnl_store_h[(q, mode, k)].append((int(ts[i]), pnl_hit_h))
                        else:
                            # inverted: TP is adverse move (|MAE|), SL is favorable (MFE)
                            tp0 = sl_base
                            sl0 = tp_base
                            tp0_h = sl_base_h
                            sl0_h = tp_base_h
                            if tp0 < k * sl0:
                                continue
                            tp = tp0 * k
                            sl = sl0 * k
                            hit = "none"
                            pnl_hit = 0.0
                            for val in curve:
                                if val <= -tp:
                                    hit = "tp"
                                    pnl_hit = val
                                    break
                                if val >= sl:
                                    hit = "sl"
                                    pnl_hit = val
                                    break
                            counts[(q, mode, k)]["tp" if hit == "tp" else "sl" if hit == "sl" else "none"] += 1
                            pnl_store[(q, mode, k)].append((int(ts[i]), pnl_hit))

                            if tp0_h < k * sl0_h:
                                continue
                            tp_h = tp0_h * k
                            sl_h = sl0_h * k
                            hit_h = "none"
                            pnl_hit_h = 0.0
                            for val in curve_h:
                                if val <= -tp_h:
                                    hit_h = "tp"
                                    pnl_hit_h = val
                                    break
                                if val >= sl_h:
                                    hit_h = "sl"
                                    pnl_hit_h = val
                                    break
                            counts_h[(q, mode, k)]["tp" if hit_h == "tp" else "sl" if hit_h == "sl" else "none"] += 1
                            pnl_store_h[(q, mode, k)].append((int(ts[i]), pnl_hit_h))

            last_entry = i

    # Summary tables
    summary_rows = []
    for q in PROFILES:
        for mode in MODES:
            for k in K_VALUES:
                c = counts[(q, mode, k)]
                tot = sum(c.values())
                summary_rows.append(
                    {
                        "profile": f"P{q}/P{q}",
                        "mode": mode,
                        "variant": "active",
                        "k": k,
                        "trades": tot,
                        "tp_first": c["tp"],
                        "sl_first": c["sl"],
                        "none": c["none"],
                        "tp_rate": c["tp"] / tot if tot else 0.0,
                        "sl_rate": c["sl"] / tot if tot else 0.0,
                    }
                )
                ch = counts_h[(q, mode, k)]
                toth = sum(ch.values())
                summary_rows.append(
                    {
                        "profile": f"P{q}/P{q}",
                        "mode": mode,
                        "variant": "hedged",
                        "k": k,
                        "trades": toth,
                        "tp_first": ch["tp"],
                        "sl_first": ch["sl"],
                        "none": ch["none"],
                        "tp_rate": ch["tp"] / toth if toth else 0.0,
                        "sl_rate": ch["sl"] / toth if toth else 0.0,
                    }
                )

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(os.path.join(OUT_DIR, "m15_mom_first_hit_profiles_summary.csv"), index=False)

    pnl_rows = []
    for q in PROFILES:
        for mode in MODES:
            for k in K_VALUES:
                ts_pnl = pnl_store[(q, mode, k)]
                if ts_pnl:
                    pnl = np.array([p for _, p in ts_pnl], dtype=float)
                    pnl_rows.append(
                        {
                            "profile": f"P{q}/P{q}",
                            "mode": mode,
                            "variant": "active",
                            "k": k,
                            "trades": len(pnl),
                            "mean_pnl": float(pnl.mean()),
                            "median_pnl": float(np.median(pnl)),
                            "total_pnl": float(pnl.sum()),
                            "win_rate": float((pnl > 0).mean() * 100.0),
                            "max_dd": _max_dd(ts_pnl),
                        }
                    )
                ts_pnl_h = pnl_store_h[(q, mode, k)]
                if ts_pnl_h:
                    pnl_h = np.array([p for _, p in ts_pnl_h], dtype=float)
                    pnl_rows.append(
                        {
                            "profile": f"P{q}/P{q}",
                            "mode": mode,
                            "variant": "hedged",
                            "k": k,
                            "trades": len(pnl_h),
                            "mean_pnl": float(pnl_h.mean()),
                            "median_pnl": float(np.median(pnl_h)),
                            "total_pnl": float(pnl_h.sum()),
                            "win_rate": float((pnl_h > 0).mean() * 100.0),
                            "max_dd": _max_dd(ts_pnl_h),
                        }
                    )

    pnl_out = pd.DataFrame(pnl_rows)
    pnl_out.to_csv(os.path.join(OUT_DIR, "m15_mom_first_hit_profiles_pnl.csv"), index=False)

    # Streak diagnostics (active only)
    streak_rows = []
    for q in PROFILES:
        for mode in MODES:
            for k in K_VALUES:
                ts_pnl = pnl_store[(q, mode, k)]
                if not ts_pnl:
                    continue
                df_st = pd.DataFrame(ts_pnl, columns=["timestamp", "pnl"]).sort_values("timestamp")
                hits = df_st["pnl"].to_numpy()
                # SL hit if pnl < 0, TP if pnl > 0
                sl_flags = hits < 0
                # max consecutive SL streak
                max_sl = 0
                cur = 0
                for f in sl_flags:
                    if f:
                        cur += 1
                        max_sl = max(max_sl, cur)
                    else:
                        cur = 0
                # max consecutive loss streak (same as SL here)
                max_loss = max_sl
                streak_rows.append(
                    {
                        "profile": f"P{q}/P{q}",
                        "mode": mode,
                        "variant": "active",
                        "k": k,
                        "trades": len(hits),
                        "max_sl_streak": max_sl,
                        "max_loss_streak": max_loss,
                    }
                )

    streak_out = pd.DataFrame(streak_rows)
    streak_out.to_csv(os.path.join(OUT_DIR, "m15_mom_first_hit_profiles_streaks.csv"), index=False)

    print("Saved:")
    print("- data/analysis/m15_mom_first_hit_profiles_summary.csv")
    print("- data/analysis/m15_mom_first_hit_profiles_pnl.csv")
    print("- data/analysis/m15_mom_first_hit_profiles_streaks.csv")


if __name__ == "__main__":
    main()

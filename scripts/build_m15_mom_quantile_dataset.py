#!/usr/bin/env python3
"""
Build M15 MOM quantile dataset with MFE/MAE targets.
Targets computed for both:
 - active-leg PnL path
 - hedged PnL path (level-beta)

Output:
 - data/analysis/m15_mom_quantile_dataset.csv
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3 as m15

DATA_PATH = "data/meta_model/events_m15_8yr_v3_dual.csv"
OUT_DIR = "data/analysis"
OUT_PATH = os.path.join(OUT_DIR, "m15_mom_quantile_dataset.csv")

THRESH_MOM = 1.5
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500
HEDGE_CLIP = 10.0


def _exit_hit(direction: int, z: float) -> bool:
    # MOM only
    if direction == 1:
        return z < 0 or z > STOP_LEVEL
    return z > 0 or z < -STOP_LEVEL


def _hedge_ratio(active_leg: str, beta: float) -> float:
    if active_leg == "Y":
        ratio = beta
    else:
        ratio = 0.0 if abs(beta) < 1e-6 else 1.0 / beta
    return float(np.clip(ratio, -HEDGE_CLIP, HEDGE_CLIP))


def _mfe_mae(pnl_path: np.ndarray) -> tuple[float, float]:
    if len(pnl_path) == 0:
        return 0.0, 0.0
    curve = np.cumsum(pnl_path)
    return float(np.max(curve)), float(np.min(curve))


def _simulate_mom_trades() -> pd.DataFrame:
    rows = []
    for name, fx, fy, cx, cy, _, _ in m15.PAIRS:
        df = m15.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()

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
            active = y if active_leg == "Y" else x
            other = x if active_leg == "Y" else y

            end = min(i + MAX_HOLD, len(z_scores) - 1)
            exit_idx = end

            d_active = []
            d_other = []
            hedge_ratios = []

            for j in range(i + 1, end + 1):
                d_active.append(active[j] - active[j - 1])
                d_other.append(other[j] - other[j - 1])
                hedge_ratios.append(_hedge_ratio(active_leg, betas[j]))

                if _exit_hit(direction, z_scores[j]):
                    exit_idx = j
                    break

            d_active = np.asarray(d_active, dtype=float)
            d_other = np.asarray(d_other, dtype=float)
            hedge_ratios = np.asarray(hedge_ratios, dtype=float)

            pnl_path_active = direction * d_active * 10000.0
            pnl_path_hedged = direction * (d_active - hedge_ratios * d_other) * 10000.0

            mfe_active, mae_active = _mfe_mae(pnl_path_active)
            mfe_hedged, mae_hedged = _mfe_mae(pnl_path_hedged)

            rows.append(
                {
                    "pair": name,
                    "timestamp": ts[i],
                    "side": "LONG" if direction == 1 else "SHORT",
                    "active_leg": active_leg,
                    "duration_bars": int(exit_idx - i),
                    "mfe_bps": mfe_active,
                    "mae_bps": mae_active,
                    "mfe_bps_hedged": mfe_hedged,
                    "mae_bps_hedged": mae_hedged,
                }
            )
            last_entry = i

    return pd.DataFrame(rows)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    targets = _simulate_mom_trades()
    if targets.empty:
        raise SystemExit("No MOM trades generated.")

    events = pd.read_csv(DATA_PATH)
    events = events[events["strategy_type"] == "MOM"].copy()

    # Normalize join keys
    events["timestamp"] = events["timestamp"].astype("int64")
    targets["timestamp"] = targets["timestamp"].astype("int64")

    merged = events.merge(
        targets,
        on=["pair", "timestamp", "side", "active_leg"],
        how="left",
        validate="one_to_one",
    )

    missing = merged["mfe_bps"].isna().mean()
    if missing > 0:
        print(f"[WARN] Missing target coverage: {missing:.2%}")

    merged.to_csv(OUT_PATH, index=False)
    print(f"Saved: {OUT_PATH}")


if __name__ == "__main__":
    main()

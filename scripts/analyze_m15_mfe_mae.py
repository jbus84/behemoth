#!/usr/bin/env python3
"""
Compute MFE/MAE per trade (M15) for MOM/REV by pair.
Uses the standard 2-leg Kalman + z-score rules.

Outputs:
 - data/analysis/m15_mfe_mae_by_pair.csv
 - data/analysis/m15_mfe_mae_overall.csv
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from pipelines import build_events_m15 as m15

OUT_DIR = "data/analysis"

THRESH_MOM = 1.5
THRESH_REV = 2.5
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500


def _exit_hit(strategy_type: str, direction: int, z: float) -> bool:
    if strategy_type == "MOM":
        if direction == 1:
            return z < 0 or z > STOP_LEVEL
        return z > 0 or z < -STOP_LEVEL
    # REV
    if direction == 1:
        return z > 0 or z < -STOP_LEVEL
    return z < 0 or z > STOP_LEVEL


def _trade_path(
    entry_idx: int,
    direction: int,
    strategy_type: str,
    y: np.ndarray,
    x: np.ndarray,
    z_scores: np.ndarray,
    active_leg: str,
) -> dict:
    active = y if active_leg == "Y" else x

    d_active = []
    end = min(entry_idx + MAX_HOLD, len(z_scores) - 1)
    exit_idx = end

    for i in range(entry_idx + 1, end + 1):
        d_active.append(active[i] - active[i - 1])
        if _exit_hit(strategy_type, direction, z_scores[i]):
            exit_idx = i
            break

    return {"d_active": np.asarray(d_active), "exit_idx": exit_idx}


def _mfe_mae(pnl_path: np.ndarray) -> tuple[float, float]:
    if len(pnl_path) == 0:
        return 0.0, 0.0
    curve = np.cumsum(pnl_path)
    return float(np.max(curve)), float(np.min(curve))


def _summary_stats(values: list[float]) -> dict:
    if not values:
        return dict(mean=0.0, p40=0.0, p60=0.0)
    arr = np.asarray(values, dtype=float)
    return dict(
        mean=float(np.mean(arr)),
        p40=float(np.percentile(arr, 40)),
        p60=float(np.percentile(arr, 60)),
    )


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    rows = []
    overall = defaultdict(list)

    for name, fx, fy, cx, cy, _, _ in m15.PAIRS:
        df = m15.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        betas, errors, _ = m15.compute_kalman_states(y, x)
        z_scores = m15.compute_z_scores(errors)

        pair_stats = {"pair": name}
        for strat in ["MOM", "REV"]:
            mfe_list = []
            mae_list = []
            last_entry = 0
            for i in range(500, len(y) - 2):
                z = z_scores[i]
                beta = betas[i]
                if beta < 0.98:
                    active_leg = "Y"
                elif beta > 1.02:
                    active_leg = "X"
                else:
                    continue

                if strat == "MOM":
                    if abs(z) < THRESH_MOM or i - last_entry < MIN_GAP:
                        continue
                    direction = 1 if z > 0 else -1
                else:
                    if abs(z) < THRESH_REV or i - last_entry < MIN_GAP:
                        continue
                    direction = -1 if z > 0 else 1

                path = _trade_path(i, direction, strat, y, x, z_scores, active_leg)
                pnl_path = direction * path["d_active"] * 10000.0
                mfe, mae = _mfe_mae(pnl_path)
                mfe_list.append(mfe)
                mae_list.append(mae)
                last_entry = i

            mfe_stats = _summary_stats(mfe_list)
            mae_stats = _summary_stats(mae_list)
            pair_stats.update(
                {
                    f"{strat}_trades": int(len(mfe_list)),
                    f"{strat}_mfe_mean": mfe_stats["mean"],
                    f"{strat}_mfe_p40": mfe_stats["p40"],
                    f"{strat}_mfe_p60": mfe_stats["p60"],
                    f"{strat}_mae_mean": mae_stats["mean"],
                    f"{strat}_mae_p40": mae_stats["p40"],
                    f"{strat}_mae_p60": mae_stats["p60"],
                }
            )

            overall[f"{strat}_mfe"].extend(mfe_list)
            overall[f"{strat}_mae"].extend(mae_list)
            overall[f"{strat}_trades"].append(len(mfe_list))

        rows.append(pair_stats)

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "m15_mfe_mae_by_pair.csv"), index=False)

    # overall summary
    overall_rows = []
    for strat in ["MOM", "REV"]:
        mfe_stats = _summary_stats(overall[f"{strat}_mfe"])
        mae_stats = _summary_stats(overall[f"{strat}_mae"])
        overall_rows.append(
            {
                "strategy_type": strat,
                "trades": int(np.sum(overall[f"{strat}_trades"])) if overall[f"{strat}_trades"] else 0,
                "mfe_mean": mfe_stats["mean"],
                "mfe_p40": mfe_stats["p40"],
                "mfe_p60": mfe_stats["p60"],
                "mae_mean": mae_stats["mean"],
                "mae_p40": mae_stats["p40"],
                "mae_p60": mae_stats["p60"],
            }
        )

    pd.DataFrame(overall_rows).to_csv(os.path.join(OUT_DIR, "m15_mfe_mae_overall.csv"), index=False)
    print("Saved:")
    print("- data/analysis/m15_mfe_mae_by_pair.csv")
    print("- data/analysis/m15_mfe_mae_overall.csv")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Analyze REV trade Z-score excursions (favorable/adverse) using M15 data.

Definitions are in Z-score distance to zero:
- favorable_move: entry_abs - min_abs (movement toward mean)
- adverse_move: max_abs - entry_abs (movement away from mean)

Outputs:
- data/analysis/m15_rev_z_excursions.csv
- data/analysis/m15_rev_z_excursions_overall.csv
- data/analysis/m15_rev_z_excursions_by_side.csv
- data/analysis/m15_rev_z_excursions_by_pair.csv
- data/analysis/m15_rev_z_excursions_by_entry_bin.csv
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from pipelines import build_events_m15 as m15

OUT_DIR = "data/analysis"

THRESH_REV = 2.5
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500

ENTRY_BINS = [2.5, 3.0, 3.5, 4.0, 5.0, 10.0]


def _exit_reason(direction: int, z: float) -> str | None:
    # REV: direction is opposite sign of entry z
    if direction == 1:  # Long
        if z > 0:
            return "Z0"
        if z < -STOP_LEVEL:
            return "ZSTOP"
    else:  # Short
        if z < 0:
            return "Z0"
        if z > STOP_LEVEL:
            return "ZSTOP"
    return None


def _summarize(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if not group_cols:
        base = {
            "favorable_move_count": [df["favorable_move"].count()],
            "favorable_move_mean": [df["favorable_move"].mean()],
            "favorable_move_median": [df["favorable_move"].median()],
            "adverse_move_mean": [df["adverse_move"].mean()],
            "adverse_move_median": [df["adverse_move"].median()],
            "favorable_move_pct_mean": [df["favorable_move_pct"].mean()],
            "favorable_move_pct_median": [df["favorable_move_pct"].median()],
            "adverse_move_pct_mean": [df["adverse_move_pct"].mean()],
            "adverse_move_pct_median": [df["adverse_move_pct"].median()],
        }
        overall = pd.DataFrame(base)
        for q in [0.2, 0.4, 0.6, 0.8]:
            overall[f"favorable_move_p{int(q * 100)}"] = df["favorable_move"].quantile(q)
            overall[f"adverse_move_p{int(q * 100)}"] = df["adverse_move"].quantile(q)
        return overall

    agg = {
        "favorable_move": ["count", "mean", "median"],
        "adverse_move": ["mean", "median"],
        "favorable_move_pct": ["mean", "median"],
        "adverse_move_pct": ["mean", "median"],
    }
    summary = df.groupby(group_cols, dropna=False).agg(agg)
    summary.columns = ["_".join(c).strip("_") for c in summary.columns]

    for q in [0.2, 0.4, 0.6, 0.8]:
        summary[f"favorable_move_p{int(q * 100)}"] = (
            df.groupby(group_cols)["favorable_move"].quantile(q)
        )
        summary[f"adverse_move_p{int(q * 100)}"] = (
            df.groupby(group_cols)["adverse_move"].quantile(q)
        )

    return summary.reset_index()


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    rows: list[dict[str, object]] = []

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
        for i in range(500, len(z_scores) - 1):
            z = float(z_scores[i])
            if abs(z) < THRESH_REV or i - last_entry < MIN_GAP:
                continue

            direction = -1 if z > 0 else 1  # REV: fade the move
            side = "LONG" if direction == 1 else "SHORT"

            entry_abs = abs(z)
            min_abs = entry_abs
            max_abs = entry_abs
            min_idx = 0
            max_idx = 0
            exit_idx = None
            exit_reason = "TIME"

            end = min(i + MAX_HOLD, len(z_scores) - 1)
            for j in range(i + 1, end + 1):
                z_abs = abs(float(z_scores[j]))
                if z_abs < min_abs:
                    min_abs = z_abs
                    min_idx = j - i
                if z_abs > max_abs:
                    max_abs = z_abs
                    max_idx = j - i

                reason = _exit_reason(direction, float(z_scores[j]))
                if reason:
                    exit_idx = j
                    exit_reason = reason
                    break

            if exit_idx is None:
                exit_idx = end

            exit_z = float(z_scores[exit_idx])
            duration = int(exit_idx - i)
            favorable_move = float(entry_abs - min_abs)
            adverse_move = float(max_abs - entry_abs)
            favorable_pct = float(favorable_move / entry_abs) if entry_abs > 0 else 0.0
            adverse_pct = float(adverse_move / entry_abs) if entry_abs > 0 else 0.0

            rows.append(
                {
                    "pair": name,
                    "timestamp": int(ts[i]),
                    "side": side,
                    "entry_z": z,
                    "entry_z_abs": entry_abs,
                    "min_abs": min_abs,
                    "max_abs": max_abs,
                    "favorable_move": favorable_move,
                    "adverse_move": adverse_move,
                    "favorable_move_pct": favorable_pct,
                    "adverse_move_pct": adverse_pct,
                    "min_idx": min_idx,
                    "max_idx": max_idx,
                    "exit_z": exit_z,
                    "exit_reason": exit_reason,
                    "duration_bars": duration,
                }
            )

            last_entry = i

    df = pd.DataFrame(rows)
    if df.empty:
        print("No REV trades found.")
        return

    df["entry_bin"] = pd.cut(
        df["entry_z_abs"],
        bins=ENTRY_BINS,
        right=True,
        include_lowest=True,
    )

    df.to_csv(os.path.join(OUT_DIR, "m15_rev_z_excursions.csv"), index=False)

    overall = _summarize(df, [])
    overall.to_csv(os.path.join(OUT_DIR, "m15_rev_z_excursions_overall.csv"), index=False)

    by_side = _summarize(df, ["side"])
    by_side.to_csv(os.path.join(OUT_DIR, "m15_rev_z_excursions_by_side.csv"), index=False)

    by_pair = _summarize(df, ["pair"])
    by_pair.to_csv(os.path.join(OUT_DIR, "m15_rev_z_excursions_by_pair.csv"), index=False)

    by_bin = _summarize(df, ["entry_bin"])
    by_bin.to_csv(os.path.join(OUT_DIR, "m15_rev_z_excursions_by_entry_bin.csv"), index=False)

    print("Saved:")
    print("- data/analysis/m15_rev_z_excursions.csv")
    print("- data/analysis/m15_rev_z_excursions_overall.csv")
    print("- data/analysis/m15_rev_z_excursions_by_side.csv")
    print("- data/analysis/m15_rev_z_excursions_by_pair.csv")
    print("- data/analysis/m15_rev_z_excursions_by_entry_bin.csv")


if __name__ == "__main__":
    main()

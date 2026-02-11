#!/usr/bin/env python3
"""
Recompute extreme trade asymmetry after applying stability filter
(pairs negative in >=50% of years are removed).
Outputs:
- data/analysis/m5_extremes_after_stability.csv
- data/analysis/m15_extremes_after_stability.csv
"""

from __future__ import annotations

import os
import pandas as pd

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/events/events_m5_8yr_v3_mom.csv"),
    ("m15", "data/events/events_m15_8yr_v3_mom.csv"),
]


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path in CONFIGS:
        df = pd.read_csv(path, usecols=["pair", "timestamp", "pnl_bps"])
        df["timestamp"] = df["timestamp"].astype("int64")
        df["year"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce").dt.year

        by = df.groupby(["pair", "year"]).agg(total_pnl=("pnl_bps", "sum")).reset_index()
        pivot = by.pivot(index="pair", columns="year", values="total_pnl").fillna(0.0)
        neg_ratio = (pivot < 0).sum(axis=1) / max(len(pivot.columns), 1)
        remove_pairs = set(neg_ratio[neg_ratio >= 0.5].index)

        filtered = df[~df["pair"].isin(remove_pairs)].copy()

        q_hi = filtered["pnl_bps"].quantile(0.999)
        q_lo = filtered["pnl_bps"].quantile(0.001)

        extreme = filtered[(filtered["pnl_bps"] >= q_hi) | (filtered["pnl_bps"] <= q_lo)].copy()
        extreme["is_win"] = extreme["pnl_bps"] > 0

        agg = extreme.groupby("pair").agg(
            extreme_count=("pair", "count"),
            extreme_win_rate=("is_win", "mean"),
            extreme_mean=("pnl_bps", "mean"),
            extreme_mean_win=("pnl_bps", lambda s: s[s > 0].mean() if (s > 0).any() else 0.0),
            extreme_mean_loss=("pnl_bps", lambda s: s[s <= 0].mean() if (s <= 0).any() else 0.0),
        ).reset_index()
        agg["loss_bias"] = agg["extreme_mean_loss"].abs() - agg["extreme_mean_win"].abs()
        agg = agg.sort_values("extreme_count", ascending=False)

        out_path = os.path.join(OUT_DIR, f"{label}_extremes_after_stability.csv")
        agg.to_csv(out_path, index=False)
        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

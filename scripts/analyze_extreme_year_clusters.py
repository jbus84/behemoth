#!/usr/bin/env python3
"""
Analyze extreme trade clustering by year.
Outputs:
- data/analysis/m5_extreme_year_clusters.csv
- data/analysis/m15_extreme_year_clusters.csv
"""

from __future__ import annotations

import os
import pandas as pd

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv"),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv"),
]


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path in CONFIGS:
        df = pd.read_csv(path, usecols=["timestamp", "pnl_bps"])
        df["timestamp"] = df["timestamp"].astype("int64")
        df["year"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce").dt.year

        q_hi = df["pnl_bps"].quantile(0.999)
        q_lo = df["pnl_bps"].quantile(0.001)

        df["extreme"] = (df["pnl_bps"] >= q_hi) | (df["pnl_bps"] <= q_lo)

        agg = df.groupby("year").agg(
            trades=("pnl_bps", "count"),
            extreme_count=("extreme", "sum"),
            extreme_rate=("extreme", "mean"),
            extreme_mean=("pnl_bps", lambda s: s[(s >= q_hi) | (s <= q_lo)].mean()),
        ).reset_index()

        out_path = os.path.join(OUT_DIR, f"{label}_extreme_year_clusters.csv")
        agg.to_csv(out_path, index=False)
        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

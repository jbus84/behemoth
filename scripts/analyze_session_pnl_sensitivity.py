#!/usr/bin/env python3
"""
Session-wise PnL sensitivity by hour and by outlier-heavy hours.
Outputs:
- data/analysis/m5_session_pnl_sensitivity.csv
- data/analysis/m15_session_pnl_sensitivity.csv
"""

from __future__ import annotations

import os
import pandas as pd

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/events/events_m5_8yr_v3_mom.csv"),
    ("m15", "data/events/events_m15_8yr_v3_mom.csv"),
]

OUTLIER_HOURS = {2, 8, 10, 14, 20}


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path in CONFIGS:
        df = pd.read_csv(path, usecols=["timestamp", "pnl_bps"])
        df["timestamp"] = df["timestamp"].astype("int64")
        df["hour"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce").dt.hour
        df["outlier_hour"] = df["hour"].isin(OUTLIER_HOURS)

        by_hour = df.groupby("hour").agg(
            trades=("hour", "count"),
            mean_pnl=("pnl_bps", "mean"),
            total_pnl=("pnl_bps", "sum"),
        ).reset_index()

        by_flag = df.groupby("outlier_hour").agg(
            trades=("outlier_hour", "count"),
            mean_pnl=("pnl_bps", "mean"),
            total_pnl=("pnl_bps", "sum"),
        ).reset_index()

        # Merge summary into one file for convenience
        by_hour["subset"] = "by_hour"
        by_flag["subset"] = by_flag["outlier_hour"].map({True: "outlier_hours", False: "non_outlier_hours"})
        by_flag = by_flag.rename(columns={"outlier_hour": "hour"})
        out = pd.concat([by_hour, by_flag], ignore_index=True)

        out.to_csv(os.path.join(OUT_DIR, f"{label}_session_pnl_sensitivity.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_session_pnl_sensitivity.csv")


if __name__ == "__main__":
    main()

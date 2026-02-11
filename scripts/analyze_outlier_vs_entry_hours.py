#!/usr/bin/env python3
"""
Compare outlier hour distribution vs entry hour distribution.
Outputs:
- data/analysis/m5_outlier_vs_entry_hours.csv
- data/analysis/m15_outlier_vs_entry_hours.csv
"""

from __future__ import annotations

import os
import pandas as pd

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/events/events_m5_8yr_v3_mom.csv", "data/analysis/m5_outlier_tradeability.csv"),
    ("m15", "data/events/events_m15_8yr_v3_mom.csv", "data/analysis/m15_outlier_tradeability.csv"),
]


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, events_path, outlier_path in CONFIGS:
        events = pd.read_csv(events_path, usecols=["timestamp"])
        events["timestamp"] = events["timestamp"].astype("int64")
        events["hour"] = pd.to_datetime(events["timestamp"], unit="ns", utc=True, errors="coerce").dt.hour

        outliers = pd.read_csv(outlier_path, usecols=["timestamp", "hour"])
        # outlier file already has hour; keep both for consistency
        if "hour" not in outliers.columns:
            outliers["hour"] = pd.to_datetime(outliers["timestamp"], unit="ns", utc=True, errors="coerce").dt.hour

        entry_counts = events["hour"].value_counts().sort_index()
        outlier_counts = outliers["hour"].value_counts().sort_index()
        hours = sorted(set(entry_counts.index).union(outlier_counts.index))

        rows = []
        for h in hours:
            e = int(entry_counts.get(h, 0))
            o = int(outlier_counts.get(h, 0))
            rows.append(
                {
                    "hour": h,
                    "entry_count": e,
                    "outlier_count": o,
                    "entry_share": e / entry_counts.sum() if entry_counts.sum() else 0.0,
                    "outlier_share": o / outlier_counts.sum() if outlier_counts.sum() else 0.0,
                }
            )

        df = pd.DataFrame(rows)
        df.to_csv(os.path.join(OUT_DIR, f"{label}_outlier_vs_entry_hours.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_outlier_vs_entry_hours.csv")


if __name__ == "__main__":
    main()

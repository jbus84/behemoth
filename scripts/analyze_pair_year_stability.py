#!/usr/bin/env python3
"""
Pair stability analysis: per-year trade count and PnL contribution.
Outputs:
- data/analysis/m5_pair_year_stability.csv
- data/analysis/m15_pair_year_stability.csv
- data/analysis/pair_year_stability_summary.csv
"""

from __future__ import annotations

import os
import pandas as pd
import numpy as np

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv"),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv"),
]


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    summary_rows = []

    for label, path in CONFIGS:
        df = pd.read_csv(path, usecols=["pair", "timestamp", "pnl_bps"])
        df["timestamp"] = df["timestamp"].astype("int64")
        df["year"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce").dt.year

        by = df.groupby(["pair", "year"]).agg(
            trades=("pair", "count"),
            total_pnl=("pnl_bps", "sum"),
            mean_pnl=("pnl_bps", "mean"),
        ).reset_index()

        out_path = os.path.join(OUT_DIR, f"{label}_pair_year_stability.csv")
        by.to_csv(out_path, index=False)

        # summary: fraction of years with negative PnL per pair
        years = sorted(df["year"].dropna().unique())
        summary = by.pivot(index="pair", columns="year", values="total_pnl").fillna(0.0)
        neg_years = (summary < 0).sum(axis=1)
        neg_ratio = (neg_years / max(len(years), 1)).sort_values(ascending=False)
        top = neg_ratio.head(5)
        summary_rows.append(
            {
                "timeframe": label,
                "pairs": int(summary.shape[0]),
                "years": int(len(years)),
                "pairs_neg_years>=0.5": int((neg_ratio >= 0.5).sum()),
                "worst_pair": top.index[0] if len(top) else "",
                "worst_pair_neg_ratio": float(top.iloc[0]) if len(top) else 0.0,
            }
        )

        print(f"Saved: {out_path}")

    pd.DataFrame(summary_rows).to_csv(os.path.join(OUT_DIR, "pair_year_stability_summary.csv"), index=False)
    print(f"Saved: {OUT_DIR}/pair_year_stability_summary.csv")


if __name__ == "__main__":
    main()

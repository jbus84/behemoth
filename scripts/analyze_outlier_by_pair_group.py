#!/usr/bin/env python3
"""
Outlier distribution by pair group (FX vs Equity/Index vs Metals/Oil).
Outputs:
- data/analysis/m5_outlier_pair_group.csv
- data/analysis/m15_outlier_pair_group.csv
"""

from __future__ import annotations

import os
import pandas as pd

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/analysis/m5_outlier_tradeability.csv"),
    ("m15", "data/analysis/m15_outlier_tradeability.csv"),
]


def group_pair(pair: str) -> str:
    if pair.startswith("SPX/"):
        return "Equity_Index"
    if pair in {"Gold/Oil", "Oil/Silver", "Gold/Silver"}:
        return "Metals_Oil"
    return "FX"


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path in CONFIGS:
        df = pd.read_csv(path, usecols=["pair", "outlier_bps"])
        df["group"] = df["pair"].map(group_pair)

        agg = df.groupby("group").agg(
            outliers=("pair", "count"),
            mean_outlier_bps=("outlier_bps", "mean"),
            p95_outlier_bps=("outlier_bps", lambda s: s.abs().quantile(0.95)),
        ).reset_index()
        agg["share"] = agg["outliers"] / agg["outliers"].sum()

        out_path = os.path.join(OUT_DIR, f"{label}_outlier_pair_group.csv")
        agg.to_csv(out_path, index=False)
        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

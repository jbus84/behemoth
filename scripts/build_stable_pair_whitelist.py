#!/usr/bin/env python3
"""
Build stable-pair whitelist (pairs negative in <50% of years).
Outputs:
- docs/analysis/stable_pairs_whitelist.md
"""

from __future__ import annotations

import os
import pandas as pd

OUTPUT_PATH = "docs/analysis/stable_pairs_whitelist.md"

CONFIGS = [
    ("M5", "data/events/events_m5_8yr_v3_mom.csv"),
    ("M15", "data/events/events_m15_8yr_v3_mom.csv"),
]


def main() -> None:
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    lines = []
    lines.append("# Stable Pair Whitelist (Negative Years < 50%)\n")

    for label, path in CONFIGS:
        df = pd.read_csv(path, usecols=["pair", "timestamp", "pnl_bps"])
        df["timestamp"] = df["timestamp"].astype("int64")
        df["year"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce").dt.year

        by = df.groupby(["pair", "year"]).agg(total_pnl=("pnl_bps", "sum")).reset_index()
        pivot = by.pivot(index="pair", columns="year", values="total_pnl").fillna(0.0)
        neg_ratio = (pivot < 0).sum(axis=1) / max(len(pivot.columns), 1)

        stable = sorted(list(neg_ratio[neg_ratio < 0.5].index))
        removed = sorted(list(neg_ratio[neg_ratio >= 0.5].index))

        lines.append(f"## {label} stable pairs ({len(stable)})")
        for p in stable:
            lines.append(f"- {p}")
        lines.append("")

        lines.append(f"## {label} excluded pairs ({len(removed)})")
        for p in removed:
            lines.append(f"- {p}")
        lines.append("")

    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

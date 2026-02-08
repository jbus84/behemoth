#!/usr/bin/env python3
"""
Analyze extreme PnL asymmetry by pair (wins vs losses).
Outputs:
- data/analysis/m5_extreme_pair_asymmetry.csv
- data/analysis/m15_extreme_pair_asymmetry.csv
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
        df = pd.read_csv(path, usecols=["pair", "pnl_bps"])
        q_hi = df["pnl_bps"].quantile(0.999)
        q_lo = df["pnl_bps"].quantile(0.001)

        extreme = df[(df["pnl_bps"] >= q_hi) | (df["pnl_bps"] <= q_lo)].copy()
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

        out_path = os.path.join(OUT_DIR, f"{label}_extreme_pair_asymmetry.csv")
        agg.to_csv(out_path, index=False)
        print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

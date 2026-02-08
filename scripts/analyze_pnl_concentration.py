#!/usr/bin/env python3
"""
PnL concentration analysis by pair (M5/M15).
Outputs:
- data/analysis/m5_pnl_concentration.csv
- data/analysis/m15_pnl_concentration.csv
- data/analysis/pnl_concentration_summary.csv
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


def _hhi(shares: np.ndarray) -> float:
    return float(np.sum(np.square(shares)))


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    summary_rows = []

    for label, path in CONFIGS:
        df = pd.read_csv(path, usecols=["pair", "pnl_bps"])
        total_pnl = df["pnl_bps"].sum()
        total_trades = len(df)

        by_pair = df.groupby("pair").agg(
            trades=("pair", "count"),
            total_pnl=("pnl_bps", "sum"),
            mean_pnl=("pnl_bps", "mean"),
        ).reset_index()
        by_pair["pnl_share"] = by_pair["total_pnl"] / total_pnl if total_pnl != 0 else 0.0
        by_pair["trade_share"] = by_pair["trades"] / total_trades if total_trades != 0 else 0.0
        by_pair = by_pair.sort_values("pnl_share", ascending=False)

        out_path = os.path.join(OUT_DIR, f"{label}_pnl_concentration.csv")
        by_pair.to_csv(out_path, index=False)

        top5_share = float(by_pair.head(5)["pnl_share"].sum()) if len(by_pair) else 0.0
        top3_share = float(by_pair.head(3)["pnl_share"].sum()) if len(by_pair) else 0.0
        top1_share = float(by_pair.head(1)["pnl_share"].sum()) if len(by_pair) else 0.0
        hhi_pnl = _hhi(by_pair["pnl_share"].to_numpy()) if len(by_pair) else 0.0
        hhi_trades = _hhi(by_pair["trade_share"].to_numpy()) if len(by_pair) else 0.0

        summary_rows.append(
            {
                "timeframe": label,
                "pairs": int(len(by_pair)),
                "total_trades": int(total_trades),
                "total_pnl": float(total_pnl),
                "top1_pnl_share": top1_share,
                "top3_pnl_share": top3_share,
                "top5_pnl_share": top5_share,
                "hhi_pnl": hhi_pnl,
                "hhi_trades": hhi_trades,
            }
        )

        print(f"Saved: {out_path}")

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(os.path.join(OUT_DIR, "pnl_concentration_summary.csv"), index=False)
    print(f"Saved: {OUT_DIR}/pnl_concentration_summary.csv")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Filter pairs with negative PnL in >=50% of years.
Recompute metrics after removing unstable pairs.
Outputs:
- data/analysis/m5_pair_stability_filter_metrics.csv
- data/analysis/m15_pair_stability_filter_metrics.csv
"""

from __future__ import annotations

import os
import sys
import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/events/events_m5_8yr_v3_mom.csv"),
    ("m15", "data/events/events_m15_8yr_v3_mom.csv"),
]


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0)
    pnl = df["pnl_bps"].to_numpy()
    ts = df["exit_ts"].to_numpy()
    return dict(
        trades=int(len(pnl)),
        mean_pnl=float(np.mean(pnl)),
        total_pnl=float(np.sum(pnl)),
        max_dd=_max_dd(pnl),
        sharpe=sharpe_daily(pnl, ts),
        sharpe_active=sharpe_daily_active(pnl, ts),
        sharpe_trade=sharpe_trade(pnl, ts),
    )


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path in CONFIGS:
        df = pd.read_csv(path)
        df["timestamp"] = df["timestamp"].astype("int64")
        df["year"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce").dt.year
        bar_minutes = 5 if label == "m5" else 15
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        by = df.groupby(["pair", "year"]).agg(total_pnl=("pnl_bps", "sum")).reset_index()
        pivot = by.pivot(index="pair", columns="year", values="total_pnl").fillna(0.0)
        neg_ratio = (pivot < 0).sum(axis=1) / max(len(pivot.columns), 1)
        remove_pairs = set(neg_ratio[neg_ratio >= 0.5].index)

        filtered = df[~df["pair"].isin(remove_pairs)].copy()

        out = pd.DataFrame([
            {"variant": "baseline", **_metrics(df)},
            {"variant": "stable_pairs_only", **_metrics(filtered), "removed_pairs": len(remove_pairs)},
        ])

        out.to_csv(os.path.join(OUT_DIR, f"{label}_pair_stability_filter_metrics.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_pair_stability_filter_metrics.csv")


if __name__ == "__main__":
    main()

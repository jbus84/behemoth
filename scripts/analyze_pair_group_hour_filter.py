#!/usr/bin/env python3
"""
Test excluding Equity/Metals trades during outlier-heavy hours.
Outputs:
- data/analysis/m5_pair_group_hour_filter.csv
- data/analysis/m15_pair_group_hour_filter.csv
"""

from __future__ import annotations

import os
import sys
import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"
OUTLIER_HOURS = {2, 8, 10, 14, 20}

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv"),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv"),
]


def group_pair(pair: str) -> str:
    if pair.startswith("SPX/"):
        return "Equity_Index"
    if pair in {"Gold/Oil", "Oil/Silver", "Gold/Silver"}:
        return "Metals_Oil"
    return "FX"


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
    ts = df["timestamp"].to_numpy()
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
        df["hour"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce").dt.hour
        df["group"] = df["pair"].map(group_pair)

        baseline = _metrics(df)

        filtered = df[~((df["group"].isin(["Equity_Index", "Metals_Oil"])) & (df["hour"].isin(OUTLIER_HOURS)))]
        filtered_metrics = _metrics(filtered)

        out = pd.DataFrame([
            {"variant": "baseline", **baseline},
            {"variant": "exclude_eq_metals_outlier_hours", **filtered_metrics},
        ])
        out.to_csv(os.path.join(OUT_DIR, f"{label}_pair_group_hour_filter.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_pair_group_hour_filter.csv")


if __name__ == "__main__":
    main()

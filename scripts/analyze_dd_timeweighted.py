#!/usr/bin/env python3
"""
Compute time-weighted drawdown (daily equity curve) and compare to trade-level DD.
Outputs:
- data/analysis/m5_dd_timeweighted.csv
- data/analysis/m15_dd_timeweighted.csv
"""

from __future__ import annotations

import os
import pandas as pd
import numpy as np

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv", 5),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv", 15),
]


def trade_level_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def daily_dd(pnls: np.ndarray, exit_ts: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    ts = pd.to_datetime(exit_ts, unit="ns", utc=True, errors="coerce")
    df = pd.DataFrame({"ts": ts, "pnl": pnls})
    df = df.dropna(subset=["ts"])
    if df.empty:
        return 0.0
    df["date"] = df["ts"].dt.normalize()
    daily = df.groupby("date")["pnl"].sum()
    full_idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_idx, fill_value=0.0)
    curve = daily.cumsum().to_numpy()
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for label, path, bar_minutes in CONFIGS:
        df = pd.read_csv(path, usecols=["timestamp", "duration_bars", "pnl_bps"])
        df["timestamp"] = df["timestamp"].astype("int64")
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        exit_ts = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        pnls = df["pnl_bps"].to_numpy()
        trade_dd = trade_level_dd(pnls)
        time_dd = daily_dd(pnls, exit_ts.to_numpy())

        out = pd.DataFrame(
            [
                {
                    "timeframe": label,
                    "trades": int(len(df)),
                    "trade_level_dd": trade_dd,
                    "daily_dd": time_dd,
                    "dd_ratio_daily_vs_trade": (time_dd / trade_dd) if trade_dd != 0 else 0.0,
                }
            ]
        )
        out.to_csv(os.path.join(OUT_DIR, f"{label}_dd_timeweighted.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_dd_timeweighted.csv")


if __name__ == "__main__":
    main()

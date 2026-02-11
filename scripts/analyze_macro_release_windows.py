#!/usr/bin/env python3
"""
Macro window sensitivity: exclude trades near common release times.
We test ±30 minutes around 08:30 and 13:30 UTC (common macro release windows).
Outputs:
- data/analysis/m5_macro_window_filter.csv
- data/analysis/m15_macro_window_filter.csv
"""

from __future__ import annotations

import os
import sys
import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"
WINDOWS = [(8, 30), (13, 30)]

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


def in_window(ts: pd.Series, hour: int, minute: int, minutes=30) -> pd.Series:
    dt = pd.to_datetime(ts, unit="ns", utc=True, errors="coerce")
    target = dt.dt.floor("D") + pd.to_timedelta(hour, unit="h") + pd.to_timedelta(minute, unit="m")
    delta = (dt - target).abs()
    return delta <= pd.to_timedelta(minutes, unit="m")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path in CONFIGS:
        df = pd.read_csv(path)
        df["timestamp"] = df["timestamp"].astype("int64")

        mask = pd.Series(False, index=df.index)
        for h, m in WINDOWS:
            mask = mask | in_window(df["timestamp"], h, m, minutes=30)

        filtered = df[~mask]

        out = pd.DataFrame([
            {"variant": "baseline", **_metrics(df)},
            {"variant": "exclude_macro_windows", **_metrics(filtered)},
        ])

        out.to_csv(os.path.join(OUT_DIR, f"{label}_macro_window_filter.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_macro_window_filter.csv")


if __name__ == "__main__":
    main()

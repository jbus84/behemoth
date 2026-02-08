#!/usr/bin/env python3
"""
Compute typical tick intervals during active hours using a sampled subset of symbols/months.
Outputs:
- data/analysis/tick_interval_active_stats_sample.csv
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd

TICK_ROOT = "/Users/danielfisher/Desktop/tick"
OUT_DIR = "data/analysis"

ACTIVE_START = 6
ACTIVE_END = 21
MAX_INTERVAL_S = 4 * 3600

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "SPXUSD", "XAUUSD", "XAGUSD"]
MONTHS = ["201901", "202003", "202406"]


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    deltas = []
    symbol_rows = []

    for sym in SYMBOLS:
        for month in MONTHS:
            path = os.path.join(TICK_ROOT, sym, f"{sym}_{month}_ticks.parquet")
            if not os.path.exists(path):
                continue
            df = pd.read_parquet(path, columns=["timestamp"])
            if df.empty:
                continue
            ts = pd.to_datetime(df["timestamp"], utc=True)
            ts_int = ts.astype("int64").to_numpy()
            if len(ts_int) < 2:
                continue
            delta = np.diff(ts_int) / 1e9
            start_ts = ts_int[:-1]
            start_hours = pd.DatetimeIndex(pd.to_datetime(start_ts, unit="ns", utc=True)).hour
            active_mask = (start_hours >= ACTIVE_START) & (start_hours < ACTIVE_END)
            mask = active_mask & (delta <= MAX_INTERVAL_S)
            sample = delta[mask]
            if len(sample):
                deltas.append(sample)
                symbol_rows.append({
                    "symbol": sym,
                    "month": month,
                    "count": int(len(sample)),
                    "p50": float(np.quantile(sample, 0.5)),
                    "p95": float(np.quantile(sample, 0.95)),
                    "p99": float(np.quantile(sample, 0.99)),
                })

    if deltas:
        all_delta = np.concatenate(deltas)
        summary = pd.DataFrame([
            {
                "symbols": ",".join(SYMBOLS),
                "months": ",".join(MONTHS),
                "count": int(len(all_delta)),
                "p50": float(np.quantile(all_delta, 0.5)),
                "p95": float(np.quantile(all_delta, 0.95)),
                "p99": float(np.quantile(all_delta, 0.99)),
            }
        ])
    else:
        summary = pd.DataFrame([
            {"symbols": ",".join(SYMBOLS), "months": ",".join(MONTHS), "count": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
        ])

    out = pd.DataFrame(symbol_rows)
    out_path = os.path.join(OUT_DIR, "tick_interval_active_stats_sample.csv")
    out.to_csv(out_path, index=False)
    summary.to_csv(out_path.replace("_sample.csv", "_summary_sample.csv"), index=False)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

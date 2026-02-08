#!/usr/bin/env python3
"""
Compute typical tick intervals during active hours using reservoir sampling.
Outputs:
- data/analysis/tick_interval_active_stats.csv
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
RESERVOIR_SIZE = 200000


def update_reservoir(res, count, value):
    count += 1
    if len(res) < RESERVOIR_SIZE:
        res.append(value)
    else:
        j = np.random.randint(0, count)
        if j < RESERVOIR_SIZE:
            res[j] = value
    return count


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    res = []
    count = 0

    symbols = [s for s in os.listdir(TICK_ROOT) if os.path.isdir(os.path.join(TICK_ROOT, s))]

    for sym in symbols:
        files = sorted([f for f in os.listdir(os.path.join(TICK_ROOT, sym)) if f.endswith("_ticks.parquet")])
        prev_last_ts = None
        for fname in files:
            path = os.path.join(TICK_ROOT, sym, fname)
            try:
                df = pd.read_parquet(path, columns=["timestamp"])
            except Exception:
                continue
            if df.empty:
                continue
            ts = pd.to_datetime(df["timestamp"], utc=True)
            ts_int = ts.astype("int64").to_numpy()

            # cross-file interval
            if prev_last_ts is not None:
                delta = (ts_int[0] - prev_last_ts) / 1e9
                if delta <= MAX_INTERVAL_S:
                    hour = pd.to_datetime(prev_last_ts, unit="ns", utc=True).hour
                    if ACTIVE_START <= hour < ACTIVE_END:
                        count = update_reservoir(res, count, float(delta))
            prev_last_ts = int(ts_int[-1])

            if len(ts_int) < 2:
                continue
            delta = np.diff(ts_int) / 1e9
            start_ts = ts_int[:-1]
            start_hours = pd.DatetimeIndex(pd.to_datetime(start_ts, unit="ns", utc=True)).hour
            active_mask = (start_hours >= ACTIVE_START) & (start_hours < ACTIVE_END)
            idx = np.where(active_mask & (delta <= MAX_INTERVAL_S))[0]
            for i in idx:
                count = update_reservoir(res, count, float(delta[i]))

    if not res:
        out = pd.DataFrame([{"count": 0, "sample": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0}])
    else:
        arr = np.array(res, dtype=float)
        out = pd.DataFrame([
            {
                "count": count,
                "sample": len(arr),
                "p50": float(np.quantile(arr, 0.5)),
                "p95": float(np.quantile(arr, 0.95)),
                "p99": float(np.quantile(arr, 0.99)),
            }
        ])

    out.to_csv(os.path.join(OUT_DIR, "tick_interval_active_stats.csv"), index=False)
    print(f"Saved: {OUT_DIR}/tick_interval_active_stats.csv")


if __name__ == "__main__":
    main()

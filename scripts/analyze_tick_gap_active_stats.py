#!/usr/bin/env python3
"""
Compute active-hours gap duration stats (filtered to <=4h) using reservoir sampling.
Outputs:
- data/analysis/tick_gap_active_stats.csv
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd

TICK_ROOT = "/Users/danielfisher/Desktop/tick"
OUT_DIR = "data/analysis"

GAP_SECONDS = [30, 60, 90, 120]
ACTIVE_START = 6
ACTIVE_END = 21
MAX_GAP_S = 4 * 3600
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

    reservoirs = {g: [] for g in GAP_SECONDS}
    counts = {g: 0 for g in GAP_SECONDS}

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

            # cross-file gap
            if prev_last_ts is not None:
                delta = (ts_int[0] - prev_last_ts) / 1e9
                if delta <= MAX_GAP_S:
                    start_hour = pd.to_datetime(prev_last_ts, unit="ns", utc=True).hour
                    if ACTIVE_START <= start_hour < ACTIVE_END:
                        for g in GAP_SECONDS:
                            if delta > g:
                                counts[g] = update_reservoir(reservoirs[g], counts[g], delta)
            prev_last_ts = int(ts_int[-1])

            # intra-file gaps
            delta = np.diff(ts_int) / 1e9
            if len(delta) == 0:
                continue
            start_ts = ts_int[:-1]
            start_hours = pd.DatetimeIndex(pd.to_datetime(start_ts, unit="ns", utc=True)).hour
            active_mask = (start_hours >= ACTIVE_START) & (start_hours < ACTIVE_END)

            for g in GAP_SECONDS:
                mask = (delta > g) & (delta <= MAX_GAP_S) & active_mask
                idx = np.where(mask)[0]
                for i in idx:
                    counts[g] = update_reservoir(reservoirs[g], counts[g], float(delta[i]))

    rows = []
    for g in GAP_SECONDS:
        res = np.array(reservoirs[g], dtype=float)
        if len(res) == 0:
            rows.append({"gap_s": g, "count": counts[g], "sample": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0})
            continue
        rows.append({
            "gap_s": g,
            "count": counts[g],
            "sample": len(res),
            "p50": float(np.quantile(res, 0.5)),
            "p95": float(np.quantile(res, 0.95)),
            "p99": float(np.quantile(res, 0.99)),
        })

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "tick_gap_active_stats.csv"), index=False)
    print(f"Saved: {OUT_DIR}/tick_gap_active_stats.csv")


if __name__ == "__main__":
    main()

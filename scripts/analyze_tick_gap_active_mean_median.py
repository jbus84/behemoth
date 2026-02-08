#!/usr/bin/env python3
"""
Compute mean/median gap sizes for active-hours gaps (<=4h).
Outputs:
- data/analysis/tick_gap_active_mean_median.csv
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
SAMPLE_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "SPXUSD", "XAUUSD", "XAGUSD"]
SAMPLE_MONTHS = ["201901", "202003", "202406"]


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

    sample_mode = os.environ.get("SAMPLE", "0") == "1"
    reservoirs = {g: [] for g in GAP_SECONDS}
    counts = {g: 0 for g in GAP_SECONDS}
    sums = {g: 0.0 for g in GAP_SECONDS}

    if sample_mode:
        symbols = [s for s in SAMPLE_SYMBOLS if os.path.isdir(os.path.join(TICK_ROOT, s))]
    else:
        symbols = [s for s in os.listdir(TICK_ROOT) if os.path.isdir(os.path.join(TICK_ROOT, s))]

    for sym in symbols:
        files = sorted([f for f in os.listdir(os.path.join(TICK_ROOT, sym)) if f.endswith("_ticks.parquet")])
        if sample_mode:
            files = [f for f in files if len(f.split("_")) > 1 and f.split("_")[1] in SAMPLE_MONTHS]
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
                    hour = pd.to_datetime(prev_last_ts, unit="ns", utc=True).hour
                    if ACTIVE_START <= hour < ACTIVE_END:
                        for g in GAP_SECONDS:
                            if delta > g:
                                sums[g] += delta
                                counts[g] = update_reservoir(reservoirs[g], counts[g], float(delta))
            prev_last_ts = int(ts_int[-1])

            if len(ts_int) < 2:
                continue
            delta = np.diff(ts_int) / 1e9
            start_ts = ts_int[:-1]
            start_hours = pd.DatetimeIndex(pd.to_datetime(start_ts, unit="ns", utc=True)).hour
            active_mask = (start_hours >= ACTIVE_START) & (start_hours < ACTIVE_END)
            for g in GAP_SECONDS:
                mask = active_mask & (delta > g) & (delta <= MAX_GAP_S)
                idx = np.where(mask)[0]
                for i in idx:
                    sums[g] += float(delta[i])
                    counts[g] = update_reservoir(reservoirs[g], counts[g], float(delta[i]))

    rows = []
    for g in GAP_SECONDS:
        res = np.array(reservoirs[g], dtype=float)
        if counts[g] == 0:
            rows.append({"gap_s": g, "count": 0, "mean": 0.0, "median": 0.0, "p95": 0.0, "p99": 0.0})
            continue
        median = float(np.quantile(res, 0.5)) if len(res) else 0.0
        p95 = float(np.quantile(res, 0.95)) if len(res) else 0.0
        p99 = float(np.quantile(res, 0.99)) if len(res) else 0.0
        mean = float(sums[g] / counts[g])
        rows.append({"gap_s": g, "count": counts[g], "mean": mean, "median": median, "p95": p95, "p99": p99})

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "tick_gap_active_mean_median.csv"), index=False)
    print(f"Saved: {OUT_DIR}/tick_gap_active_mean_median.csv")


if __name__ == "__main__":
    main()

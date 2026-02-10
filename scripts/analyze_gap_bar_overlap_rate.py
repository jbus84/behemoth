#!/usr/bin/env python3
"""
Compute fraction of bars that contain any tick gap > threshold.

Outputs:
- data/analysis/m5_gap_bar_overlap_rate.csv
- data/analysis/m15_gap_bar_overlap_rate.csv
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd

TICK_ROOT = "/Users/danielfisher/Desktop/tick"
OUT_DIR = "data/analysis"

SYMBOLS = None  # None -> all
THRESHOLDS = [30, 60, 90, 120]
MAX_GAP_S = 4 * 3600

BAR_SECONDS = {
    "m5": 300,
    "m15": 900,
}


def _symbol_from_barfile(fname: str) -> str:
    return fname.split("_")[0]


def _bar_gap_rates(symbol: str, bar_s: int, thresholds: list[int]):
    path = os.path.join(TICK_ROOT, symbol)
    if not os.path.isdir(path):
        return None
    files = sorted([f for f in os.listdir(path) if f.endswith("_ticks.parquet")])
    if not files:
        return None

    counts = {t: 0 for t in thresholds}
    total_bars = 0

    for fname in files:
        fpath = os.path.join(path, fname)
        try:
            df = pd.read_parquet(fpath, columns=["timestamp"])
        except Exception:
            continue
        if df.empty or len(df) < 2:
            continue
        ts = pd.to_datetime(df["timestamp"], utc=True).astype("int64").to_numpy()
        bar_id = (ts // (bar_s * 1_000_000_000)).astype("int64")

        # compute intrabar gaps
        dt = np.diff(ts) / 1e9
        bar_id_prev = bar_id[:-1]
        same_bar = bar_id_prev == bar_id[1:]
        if not np.any(same_bar):
            continue
        dt = dt[same_bar]
        bar_id_prev = bar_id_prev[same_bar]

        s = pd.Series(dt, index=bar_id_prev)
        max_gap = s.groupby(level=0).max()

        total_bars += len(max_gap)
        for t in thresholds:
            counts[t] += int(((max_gap > t) & (max_gap <= MAX_GAP_S)).sum())

    if total_bars == 0:
        return None

    row = {"symbol": symbol, "bars": total_bars}
    for t in thresholds:
        row[f"gap_gt_{t}_rate"] = counts[t] / total_bars
        row[f"gap_gt_{t}_count"] = counts[t]
    return row


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    symbols = SYMBOLS
    if symbols is None:
        symbols = [s for s in os.listdir(TICK_ROOT) if os.path.isdir(os.path.join(TICK_ROOT, s))]

    for label, bar_s in BAR_SECONDS.items():
        rows = []
        for sym in symbols:
            res = _bar_gap_rates(sym, bar_s, THRESHOLDS)
            if res:
                rows.append(res)

        df = pd.DataFrame(rows)
        if df.empty:
            continue
        out_path = os.path.join(OUT_DIR, f"{label}_gap_bar_overlap_rate.csv")
        df.to_csv(out_path, index=False)
        print(f"Saved {out_path}")


if __name__ == "__main__":
    main()

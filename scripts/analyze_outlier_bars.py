#!/usr/bin/env python3
"""
Outlier bar analysis per pair and overlap with trades.
Detects extreme single-bar returns using rolling std threshold.
Outputs:
- data/analysis/m5_outlier_summary.csv
- data/analysis/m15_outlier_summary.csv
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3_m5 as m5
import build_meta_dataset_v3 as m15

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv", m5),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv", m15),
]

THRESH = 8.0  # sigma
WINDOW = 500


def _pair_map(module):
    return {name: (fx, fy, cx, cy) for name, fx, fy, cx, cy, *_ in module.PAIRS}


def _load_prices(module, fx, fy, cx, cy):
    df = module.load_pair_data(fx, fy, cx, cy)
    if df is None:
        return None
    x = np.log(df["X"].to_numpy())
    y = np.log(df["Y"].to_numpy())
    ts = df["timestamp"].to_numpy()
    if np.issubdtype(ts.dtype, np.datetime64):
        ts = ts.astype("datetime64[ns]").astype("int64")
    else:
        ts = ts.astype("int64")
    return ts, x, y


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, events_path, module in CONFIGS:
        events = pd.read_csv(events_path, usecols=["pair", "timestamp", "duration_bars", "active_leg"])
        events["timestamp"] = events["timestamp"].astype("int64")

        pair_info = _pair_map(module)
        rows = []

        for pair, sub in events.groupby("pair"):
            if pair not in pair_info:
                continue
            fx, fy, cx, cy = pair_info[pair]
            loaded = _load_prices(module, fx, fy, cx, cy)
            if loaded is None:
                continue
            ts, x, y = loaded
            idx_map = {int(t): i for i, t in enumerate(ts)}

            # returns
            ret_x = np.diff(x)
            ret_y = np.diff(y)

            # rolling std
            def rolling_std(arr):
                out = np.full_like(arr, np.nan, dtype=float)
                for i in range(WINDOW, len(arr)):
                    out[i] = np.std(arr[i-WINDOW:i])
                return out

            std_x = rolling_std(ret_x)
            std_y = rolling_std(ret_y)

            # outlier bars (index in ret space = bar i vs i-1)
            out_x = np.where((np.abs(ret_x) > THRESH * std_x) & ~np.isnan(std_x))[0]
            out_y = np.where((np.abs(ret_y) > THRESH * std_y) & ~np.isnan(std_y))[0]
            outlier_idx = np.unique(np.concatenate([out_x, out_y]))
            outlier_ts = set(int(ts[i+1]) for i in outlier_idx if i+1 < len(ts))

            # overlap with trades
            overlap = 0
            total = 0
            for row in sub.itertuples(index=False):
                entry_ts = int(row.timestamp)
                entry_idx = idx_map.get(entry_ts)
                if entry_idx is None:
                    continue
                exit_idx = entry_idx + int(row.duration_bars)
                if exit_idx >= len(ts):
                    continue
                total += 1
                # quick check: any outlier timestamp within [entry, exit]
                for i in range(entry_idx + 1, exit_idx + 1):
                    if int(ts[i]) in outlier_ts:
                        overlap += 1
                        break

            rows.append(
                {
                    "pair": pair,
                    "outlier_bars": int(len(outlier_ts)),
                    "trade_count": int(total),
                    "trade_outlier_overlap": int(overlap),
                    "overlap_rate": float(overlap / total) if total else 0.0,
                }
            )

        out = pd.DataFrame(rows)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_outlier_summary.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_outlier_summary.csv")


if __name__ == "__main__":
    main()

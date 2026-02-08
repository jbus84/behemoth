#!/usr/bin/env python3
"""
Find extreme PnL outliers and their concentration.
Outputs:
- data/analysis/m5_trade_outliers_summary.csv
- data/analysis/m15_trade_outliers_summary.csv
- data/analysis/m5_trade_outliers_top.csv
- data/analysis/m15_trade_outliers_top.csv
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

WINDOW = 500
THRESH = 8.0


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


def _outlier_ts_for_pair(module, fx, fy, cx, cy):
    loaded = _load_prices(module, fx, fy, cx, cy)
    if loaded is None:
        return set()
    ts, x, y = loaded
    ret_x = np.diff(x)
    ret_y = np.diff(y)

    def rolling_std(arr):
        out = np.full_like(arr, np.nan, dtype=float)
        for i in range(WINDOW, len(arr)):
            out[i] = np.std(arr[i-WINDOW:i])
        return out

    std_x = rolling_std(ret_x)
    std_y = rolling_std(ret_y)
    out_x = np.where((np.abs(ret_x) > THRESH * std_x) & ~np.isnan(std_x))[0]
    out_y = np.where((np.abs(ret_y) > THRESH * std_y) & ~np.isnan(std_y))[0]
    out_idx = np.unique(np.concatenate([out_x, out_y]))
    return set(int(ts[i + 1]) for i in out_idx if i + 1 < len(ts))


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path, module in CONFIGS:
        df = pd.read_csv(path, usecols=["pair", "timestamp", "duration_bars", "pnl_bps", "active_leg", "side"])
        pnl = df["pnl_bps"].to_numpy()

        q_hi = np.quantile(pnl, 0.999)
        q_lo = np.quantile(pnl, 0.001)
        q_hi2 = np.quantile(pnl, 0.9999)
        q_lo2 = np.quantile(pnl, 0.0001)

        # mark extremes
        df["extreme"] = (df["pnl_bps"] >= q_hi) | (df["pnl_bps"] <= q_lo)
        df["extreme2"] = (df["pnl_bps"] >= q_hi2) | (df["pnl_bps"] <= q_lo2)

        pair_info = _pair_map(module)
        outlier_cache = {}
        overlap_flags = []

        # compute overlap with 8σ bars for extreme trades
        for row in df.itertuples(index=False):
            if not row.extreme:
                overlap_flags.append(False)
                continue
            pair = row.pair
            if pair not in outlier_cache:
                fx, fy, cx, cy = pair_info[pair]
                outlier_cache[pair] = _outlier_ts_for_pair(module, fx, fy, cx, cy)
            outs = outlier_cache[pair]
            # approximate: consider if entry ts is itself an outlier
            overlap_flags.append(int(row.timestamp) in outs)

        df["entry_outlier"] = overlap_flags

        # top 20 gains/losses
        top = pd.concat([
            df.nlargest(20, "pnl_bps"),
            df.nsmallest(20, "pnl_bps")
        ])
        top.to_csv(os.path.join(OUT_DIR, f"{label}_trade_outliers_top.csv"), index=False)

        # summary
        extreme = df[df["extreme"]]
        extreme2 = df[df["extreme2"]]

        by_pair = extreme.groupby("pair").agg(
            count=("pair", "count"),
            share=("pair", lambda s: len(s) / len(extreme) if len(extreme) else 0.0),
            mean_pnl=("pnl_bps", "mean"),
        ).reset_index().sort_values("share", ascending=False)

        summary = pd.DataFrame([
            {
                "timeframe": label,
                "pnl_p999": float(q_hi),
                "pnl_p001": float(q_lo),
                "pnl_p9999": float(q_hi2),
                "pnl_p0001": float(q_lo2),
                "extreme_count": int(len(extreme)),
                "extreme2_count": int(len(extreme2)),
                "entry_outlier_rate_extreme": float(extreme["entry_outlier"].mean()) if len(extreme) else 0.0,
                "top_pair": by_pair.iloc[0]["pair"] if len(by_pair) else "",
                "top_pair_share": float(by_pair.iloc[0]["share"]) if len(by_pair) else 0.0,
            }
        ])

        summary.to_csv(os.path.join(OUT_DIR, f"{label}_trade_outliers_summary.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_trade_outliers_summary.csv")
        print(f"Saved: {OUT_DIR}/{label}_trade_outliers_top.csv")


if __name__ == "__main__":
    main()

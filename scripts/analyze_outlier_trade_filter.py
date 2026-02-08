#!/usr/bin/env python3
"""
Filter out trades that overlap outlier bars and recompute metrics.
Outlier bars: |return| > 8 * rolling std (500-bar window).
Outputs:
- data/analysis/m5_outlier_filter_metrics.csv
- data/analysis/m15_outlier_filter_metrics.csv
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade
import build_meta_dataset_v3_m5 as m5
import build_meta_dataset_v3 as m15

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv", m5, 5),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv", m15, 15),
]

WINDOW = 500
THRESH = 8.0


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
    ts = df["exit_ts"].to_numpy()
    return dict(
        trades=int(len(pnl)),
        mean_pnl=float(np.mean(pnl)),
        total_pnl=float(np.sum(pnl)),
        max_dd=_max_dd(pnl),
        sharpe=sharpe_daily(pnl, ts),
        sharpe_active=sharpe_daily_active(pnl, ts),
        sharpe_trade=sharpe_trade(pnl, ts),
    )


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

    for label, path, module, bar_minutes in CONFIGS:
        df = pd.read_csv(path)
        df["timestamp"] = df["timestamp"].astype("int64")
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        pair_info = _pair_map(module)
        keep_rows = []

        for pair, sub in df.groupby("pair"):
            if pair not in pair_info:
                continue
            fx, fy, cx, cy = pair_info[pair]
            loaded = _load_prices(module, fx, fy, cx, cy)
            if loaded is None:
                continue
            ts, x, y = loaded
            idx_map = {int(t): i for i, t in enumerate(ts)}

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
            outlier_idx = np.unique(np.concatenate([out_x, out_y]))
            outlier_ts = set(int(ts[i+1]) for i in outlier_idx if i+1 < len(ts))

            for row in sub.itertuples(index=False):
                entry_ts = int(row.timestamp)
                entry_idx = idx_map.get(entry_ts)
                if entry_idx is None:
                    continue
                exit_idx = entry_idx + (int(row.duration_bars) - 1 if int(row.duration_bars) >= 500 else int(row.duration_bars))
                if exit_idx >= len(ts):
                    continue
                # drop if any outlier within trade window
                has_outlier = False
                for i in range(entry_idx + 1, exit_idx + 1):
                    if int(ts[i]) in outlier_ts:
                        has_outlier = True
                        break
                if not has_outlier:
                    keep_rows.append(row._asdict())

        filtered = pd.DataFrame(keep_rows)
        base_metrics = _metrics(df)
        filt_metrics = _metrics(filtered)

        out = pd.DataFrame([
            {"variant": "baseline", **base_metrics},
            {"variant": "no_outlier_bars", **filt_metrics},
        ])
        out.to_csv(os.path.join(OUT_DIR, f"{label}_outlier_filter_metrics.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_outlier_filter_metrics.csv")


if __name__ == "__main__":
    main()

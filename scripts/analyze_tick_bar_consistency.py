#!/usr/bin/env python3
"""
Tick vs bar consistency audit for sample symbols/months.
Compares tick-derived close (last mid in bucket) vs bar close.
Outputs:
- data/analysis/tick_bar_consistency.csv
"""

from __future__ import annotations

import os
import pandas as pd
import numpy as np

OUT_DIR = "data/analysis"
TICK_ROOT = "/Users/danielfisher/Desktop/tick"
BAR_ROOT_5 = "data/global_5m"
BAR_ROOT_15 = "data/global_15m"

SYMBOLS = ["EURUSD", "SPXUSD", "XAUUSD"]
MONTHS = ["201801", "202003", "202406"]
TIMEFRAMES = [5, 15]


def _load_ticks(symbol: str, month: str) -> pd.DataFrame | None:
    path = os.path.join(TICK_ROOT, symbol, f"{symbol}_{month}_ticks.parquet")
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path, columns=["timestamp", "mid"])
    return df


def _load_bars(symbol: str, tf: int) -> pd.DataFrame | None:
    root = BAR_ROOT_5 if tf == 5 else BAR_ROOT_15
    path = os.path.join(root, f"{symbol}_{tf}m.parquet")
    if not os.path.exists(path):
        return None
    close_col = f"close_{symbol}"
    df = pd.read_parquet(path, columns=["timestamp", close_col]).rename(columns={close_col: "bar_close"})
    return df


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    rows = []

    for symbol in SYMBOLS:
        for month in MONTHS:
            ticks = _load_ticks(symbol, month)
            if ticks is None:
                rows.append({"symbol": symbol, "month": month, "tf": None, "status": "missing_ticks"})
                continue

            for tf in TIMEFRAMES:
                bars = _load_bars(symbol, tf)
                if bars is None:
                    rows.append({"symbol": symbol, "month": month, "tf": tf, "status": "missing_bars"})
                    continue

                # filter bars to month
                bars = bars.copy()
                bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
                bars = bars[(bars["timestamp"].dt.strftime("%Y%m") == month)]
                if bars.empty:
                    rows.append({"symbol": symbol, "month": month, "tf": tf, "status": "no_bars_in_month"})
                    continue

                t = ticks.copy()
                t["timestamp"] = pd.to_datetime(t["timestamp"], utc=True)
                t = t[(t["timestamp"].dt.strftime("%Y%m") == month)]
                if t.empty:
                    rows.append({"symbol": symbol, "month": month, "tf": tf, "status": "no_ticks_in_month"})
                    continue

                # bucket ticks
                t["bucket"] = t["timestamp"].dt.floor(f"{tf}min")
                tick_close = t.groupby("bucket")["mid"].last().reset_index().rename(columns={"mid": "tick_close"})

                # align bars to bucket
                bars = bars.rename(columns={"timestamp": "bucket"})

                merged = pd.merge(bars, tick_close, on="bucket", how="inner")
                if merged.empty:
                    rows.append({"symbol": symbol, "month": month, "tf": tf, "status": "no_overlap"})
                    continue

                # compute errors in bps
                merged["diff_bps"] = (merged["tick_close"] - merged["bar_close"]) / merged["bar_close"] * 10000.0
                abs_err = merged["diff_bps"].abs()

                rows.append(
                    {
                        "symbol": symbol,
                        "month": month,
                        "tf": tf,
                        "status": "ok",
                        "bars_compared": int(len(merged)),
                        "mean_abs_bps": float(abs_err.mean()),
                        "p95_abs_bps": float(abs_err.quantile(0.95)),
                        "max_abs_bps": float(abs_err.max()),
                    }
                )

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "tick_bar_consistency.csv"), index=False)
    print(f"Saved: {OUT_DIR}/tick_bar_consistency.csv")


if __name__ == "__main__":
    main()

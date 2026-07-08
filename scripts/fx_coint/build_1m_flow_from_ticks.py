#!/usr/bin/env python3
"""Build 1m flow parquets from HistData tick files for use with validate_reversion_cell.py.

Output schema: bucket (datetime), mid (float), n_ticks (int)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

TICK_ROOT = Path("/Users/danielfisher/Desktop/tick")
OUT_ROOT = Path(__file__).resolve().parents[2] / "data" / "tick_bars"

SYMBOLS = [
    "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDJPY", "USDCHF",
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURCHF",
    "AUDCAD", "GBPAUD", "EURAUD", "GBPCHF", "CADJPY",
    "CHFJPY", "NZDUSD", "EURNZD", "GBPNZD", "AUDNZD",
]


def build_flow(sym: str) -> None:
    sym_dir = TICK_ROOT / sym
    files = sorted(sym_dir.glob(f"{sym}_*_ticks.parquet"))
    if not files:
        print(f"SKIP {sym}: no tick files")
        return

    print(f"Building {sym} from {len(files)} files...")
    chunks = []
    for f in files:
        df = pd.read_parquet(f, columns=["timestamp", "mid"])
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        chunks.append(df)

    ticks = pd.concat(chunks).sort_values("timestamp").reset_index(drop=True)
    ticks["bucket"] = ticks["timestamp"].dt.floor("1min")

    # 1m bars: last mid, tick count
    bars = (
        ticks.groupby("bucket")
        .agg(mid=("mid", "last"), n_ticks=("mid", "count"))
        .reset_index()
        .sort_values("bucket")
    )

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    out_path = OUT_ROOT / f"{sym}_1m_flow.parquet"
    pl.from_pandas(bars).write_parquet(out_path)
    print(f"  wrote {out_path} ({len(bars)} bars)")


def main():
    for sym in SYMBOLS:
        build_flow(sym)
    print("Done.")


if __name__ == "__main__":
    main()

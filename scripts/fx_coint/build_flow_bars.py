"""Build cached 1-min flow bars (mid/bid/ask + tick-rule flow + OFI) from raw
dukascopy ticks. Output: data/tick_bars/{sym}_1m_flow.parquet.

Usage: python scripts/fx_coint/build_flow_bars.py
"""

from __future__ import annotations

import glob
import os

import polars as pl

from scripts.fx_coint.flow_proxies import bars_from_ticks

SRC = os.path.expanduser("~/Desktop/dukascopy_ticks")
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
FREQ = "1m"
OUT = "data/tick_bars"


def build(sym: str) -> pl.DataFrame:
    files = sorted(glob.glob(f"{SRC}/{sym}/*_ticks.parquet"))
    parts = [
        bars_from_ticks(pl.read_parquet(f).select("timestamp", "bid", "ask", "mid"), FREQ)
        for f in files
    ]
    return pl.concat(parts).sort("bucket").unique(subset="bucket", keep="last")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for sym in PAIRS:
        df = build(sym)
        path = f"{OUT}/{sym}_{FREQ}_flow.parquet"
        df.write_parquet(path)
        print(f"{sym}: {df.height} bars  {df['bucket'].min()} -> {df['bucket'].max()}  -> {path}")


if __name__ == "__main__":
    main()

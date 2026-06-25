"""Build TRUE time bars from raw dukascopy ticks (last tick before each boundary).

The 1000-tick bars resampled to 15m/30m have a median 5.5-min stale close (the
last *1000-tick bar* close, not the last tick), which manufactures reversion.
This builds honest time bars: for each freq window, take the actual last tick's
bid/ask/mid. Caches to data/tick_bars/{sym}_{freq}_raw.parquet.

Usage: python build_rawtick_timebars.py            # builds 15m + 30m, all pairs
"""

from __future__ import annotations

import glob
import os

import polars as pl

SRC = "/Users/danielfisher/Desktop/dukascopy_ticks"
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
FREQS = ["15m", "30m"]
OUT = "data/tick_bars"


def build(sym: str, freq: str) -> pl.DataFrame:
    files = sorted(glob.glob(f"{SRC}/{sym}/*_ticks.parquet"))
    parts = []
    for f in files:
        lf = (
            pl.scan_parquet(f)
            .select("timestamp", "bid", "ask", "mid")
            .sort("timestamp")
            .group_by(pl.col("timestamp").dt.truncate(freq).alias("bucket"))
            .agg(
                pl.col("bid").last().alias("bid"),
                pl.col("ask").last().alias("ask"),
                pl.col("mid").last().alias("mid"),
                pl.len().alias("n_ticks"),
            )
        )
        parts.append(lf.collect())
    df = pl.concat(parts).sort("bucket").unique(subset="bucket", keep="last")
    return df


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for sym in PAIRS:
        for freq in FREQS:
            df = build(sym, freq)
            path = f"{OUT}/{sym}_{freq}_raw.parquet"
            df.write_parquet(path)
            print(f"{sym} {freq}: {df.height} bars  {df['bucket'].min()} -> {df['bucket'].max()}  -> {path}")


if __name__ == "__main__":
    main()

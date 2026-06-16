"""Honest time bars from raw dukascopy ticks.

Last *tick* before each boundary (never a tick-count resample, which leaves a
~half-bar-stale close and manufactures reversion), plus intrabar mid high/low so
the triple-barrier in labels.py can detect touches without look-ahead.
Cache: data/tick_bars/{sym}_{freq}_cluster.parquet.

Usage: python scripts/fx_cluster/bars.py        # builds hourly bars, all pairs
"""

from __future__ import annotations

import argparse
import glob
import os

import polars as pl

from scripts.fx_cluster import config


def aggregate_bars(ticks: pl.DataFrame, freq: str) -> pl.DataFrame:
    """One bar per freq bucket: last bid/ask/mid + intrabar mid high/low + tick count."""
    return (
        ticks.sort("timestamp")
        .group_by(pl.col("timestamp").dt.truncate(freq).alias("bucket"))
        .agg(
            pl.col("bid").last().alias("bid"),
            pl.col("ask").last().alias("ask"),
            pl.col("mid").last().alias("mid"),
            pl.col("mid").max().alias("mid_high"),
            pl.col("mid").min().alias("mid_low"),
            pl.len().alias("n_ticks"),
        )
    )


def build(sym: str, freq: str = config.FREQ) -> pl.DataFrame:
    files = sorted(glob.glob(f"{config.TICK_SRC}/{sym}/*_ticks.parquet"))
    if not files:
        raise FileNotFoundError(f"no tick files for {sym} under {config.TICK_SRC}")
    parts = [
        aggregate_bars(
            pl.scan_parquet(f).select("timestamp", "bid", "ask", "mid").collect(), freq
        )
        for f in files
    ]
    return pl.concat(parts).sort("bucket").unique(subset="bucket", keep="last")


def load_bars(sym: str, freq: str = config.FREQ) -> pl.DataFrame:
    return pl.read_parquet(f"{config.BAR_DIR}/{sym}_{freq}_cluster.parquet")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build honest cluster bars from raw ticks.")
    parser.add_argument("--freq", default=config.FREQ)
    args = parser.parse_args()
    os.makedirs(config.BAR_DIR, exist_ok=True)
    for sym in config.PAIRS:
        df = build(sym, args.freq)
        path = f"{config.BAR_DIR}/{sym}_{args.freq}_cluster.parquet"
        df.write_parquet(path)
        print(f"{sym} {args.freq}: {df.height} bars  {df['bucket'].min()} -> {df['bucket'].max()}  -> {path}")


if __name__ == "__main__":
    main()

"""Build cached 1-hour flow bars from the 1-min flow bars.
Output: data/tick_bars/{sym}_1h_flow.parquet.

Usage: python scripts/fx_coint/build_hourly_bars.py
"""

from __future__ import annotations

import os

import polars as pl

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
SRC_DIR = "data/tick_bars"
OUT_DIR = "data/tick_bars"


def aggregate_1h(flow_1m: pl.DataFrame) -> pl.DataFrame:
    """flow_1m cols: bucket, mid, bid, ask, flow_tick, flow_ofi, n_ticks (sorted).
    Returns 1h bars: last mid/bid/ask, summed n_ticks, mean flow, realized vol
    (std of 1-min log-returns, bps) and mean relative spread (bps)."""
    t = flow_1m.sort("bucket").with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        ((pl.col("ask") - pl.col("bid")) / pl.col("mid")).alias("relspr"),
        pl.col("bucket").dt.truncate("1h").alias("b1h"),
    )
    return (
        t.group_by("b1h")
        .agg(
            pl.col("mid").last(),
            pl.col("bid").last(),
            pl.col("ask").last(),
            pl.col("n_ticks").sum(),
            pl.col("flow_tick").mean(),
            pl.col("flow_ofi").mean(),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
            (pl.col("relspr").mean() * 1e4).alias("spread_bps"),
        )
        .rename({"b1h": "bucket"})
        .sort("bucket")
    )


def build(sym: str) -> pl.DataFrame:
    df = pl.read_parquet(f"{SRC_DIR}/{sym}_1m_flow.parquet")
    return aggregate_1h(df)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for sym in PAIRS:
        df = build(sym)
        path = f"{OUT_DIR}/{sym}_1h_flow.parquet"
        df.write_parquet(path)
        print(
            f"{sym}: {df.height} bars  {df['bucket'].min()} -> {df['bucket'].max()}  -> {path}"
        )


if __name__ == "__main__":
    main()

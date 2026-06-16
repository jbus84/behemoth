"""Aggregate 1-min flow bars into a 30m feature panel (causal within-bar stats).
Pure: no import-time side effects."""

from __future__ import annotations

import polars as pl


def aggregate_30m(flow_1m: pl.DataFrame) -> pl.DataFrame:
    """flow_1m cols: bucket, mid, bid, ask, flow_tick, flow_ofi, n_ticks (sorted).
    Returns 30m bars: last mid/bid/ask, summed n_ticks, mean flow, realized vol
    (std of 1-min log-returns, bps) and mean relative spread (bps)."""
    t = flow_1m.sort("bucket").with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        ((pl.col("ask") - pl.col("bid")) / pl.col("mid")).alias("relspr"),
        pl.col("bucket").dt.truncate("30m").alias("b30"),
    )
    return (
        t.group_by("b30")
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
        .rename({"b30": "bucket"})
        .sort("bucket")
    )

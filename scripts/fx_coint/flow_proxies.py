"""Pure quote-flow kernels: tick-rule signed flow, sizeless Cont OFI,
causal z-score, and raw-tick -> time-bar aggregation. No import-time side effects."""

from __future__ import annotations

import numpy as np
import polars as pl


def tick_rule_signs(mid: np.ndarray) -> np.ndarray:
    """Lee-Ready tick rule: +1 uptick, -1 downtick, 0-diff carries the last sign.
    First element has no prior tick -> 0."""
    d = np.sign(np.diff(mid, prepend=mid[0]))
    out = np.zeros(len(d), dtype=float)
    last = 0.0
    for i in range(len(d)):
        if d[i] != 0.0:
            last = d[i]
        out[i] = last
    return out


def quote_ofi(bid: np.ndarray, ask: np.ndarray) -> np.ndarray:
    """Sizeless Cont order-flow imbalance per tick: sign(Δbid) - sign(Δask).
    + = buy pressure (bid rising and/or ask falling)."""
    db = np.sign(np.diff(bid, prepend=bid[0]))
    da = np.sign(np.diff(ask, prepend=ask[0]))
    return db - da


def causal_zscore(x: pl.Series, span: int) -> pl.Series:
    """EWMA z-score using only information up to t-1 (mean/std shifted by one bar),
    so x_t never enters its own normalisation."""
    mean = x.ewm_mean(span=span, min_samples=span).shift(1)
    std = x.ewm_std(span=span, min_samples=span).shift(1)
    return (x - mean) / std


def bars_from_ticks(ticks: pl.DataFrame, freq: str) -> pl.DataFrame:
    """ticks: timestamp, bid, ask, mid. Build true time bars (last tick before each
    boundary) with mean tick-rule flow + mean OFI + tick count per bar."""
    t = ticks.sort("timestamp")
    t = t.with_columns(
        pl.Series("tsign", tick_rule_signs(t["mid"].to_numpy())),
        pl.Series("ofi", quote_ofi(t["bid"].to_numpy(), t["ask"].to_numpy())),
        pl.col("timestamp").dt.truncate(freq).alias("bucket"),
    )
    return (
        t.group_by("bucket")
        .agg(
            pl.col("mid").last(),
            pl.col("bid").last(),
            pl.col("ask").last(),
            pl.col("tsign").mean().alias("flow_tick"),
            pl.col("ofi").mean().alias("flow_ofi"),
            pl.len().alias("n_ticks"),
        )
        .sort("bucket")
    )

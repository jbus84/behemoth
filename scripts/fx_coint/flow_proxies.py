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

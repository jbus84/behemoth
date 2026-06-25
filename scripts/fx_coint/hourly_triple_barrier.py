"""Cost-aware triple barrier labeling for hourly FX bars.

Implements Lopez de Prado's triple barrier method with a cost-aware twist:
the upper/lower barriers are set at the round-trip transaction cost level,
so only excursions that exceed cost are labeled as +1 / -1. Sub-cost
excursions and time expiries are labeled 0.

Usage:
    from scripts.fx_coint.hourly_triple_barrier import label_hourly
    df = label_hourly(eurusd_1h, cost_bps=0.64, horizon=12)
"""

from __future__ import annotations

import numpy as np
import polars as pl

# Pepperstone Razor round-trip cost in basis points (from walkforward.py)
DEFAULT_COST_BPS: dict[str, float] = {
    "EURUSD": 0.64,   # 0.7 pips ≈ 0.64 bps at 1.10
    "GBPUSD": 0.80,   # 1.0 pip
    "AUDUSD": 0.88,   # 1.1 pips
    "USDJPY": 0.72,   # 0.8 pips (JPY: 1 pip = 0.01, so ~0.72 bps)
    "USDCHF": 0.88,   # 1.1 pips
    "USDCAD": 0.88,   # 1.1 pips
}


def _label_bar(
    mid: np.ndarray,
    bid: np.ndarray,
    ask: np.ndarray,
    i: int,
    horizon: int,
    cost_delta: float,
    multiplier: float,
) -> tuple[int, int]:
    """Label a single bar i with triple barrier.

    Returns (label, touch_bar_offset):
        label = +1 if upper hit first AND move > cost
              = -1 if lower hit first AND move > cost
              =  0 if time expires or neither barrier exceeded cost
        touch_bar_offset = bars until first touch (or horizon if no touch)
    """
    n = len(mid)
    mid[i]
    entry_bid = bid[i]
    entry_ask = ask[i]

    # Cost-aware barriers: must exceed round-trip cost × multiplier
    # Long:  need bid >= ask_entry + cost_target
    # Short: need ask <= bid_entry - cost_target
    cost_target = cost_delta * multiplier
    upper_barrier = entry_ask + cost_target
    lower_barrier = entry_bid - cost_target

    max_j = min(i + horizon + 1, n)

    upper_touch = None
    lower_touch = None

    for j in range(i + 1, max_j):
        if upper_touch is None and bid[j] >= upper_barrier:
            upper_touch = j
        if lower_touch is None and ask[j] <= lower_barrier:
            lower_touch = j
        # Early exit if both found
        if upper_touch is not None and lower_touch is not None:
            break

    if upper_touch is None and lower_touch is None:
        return 0, horizon

    if upper_touch is not None and lower_touch is not None:
        if upper_touch < lower_touch:
            return 1, upper_touch - i
        elif lower_touch < upper_touch:
            return -1, lower_touch - i
        else:
            return 0, upper_touch - i

    if upper_touch is not None:
        return 1, upper_touch - i
    else:
        return -1, lower_touch - i


def label_hourly(
    df: pl.DataFrame,
    symbol: str,
    *,
    cost_bps: float | None = None,
    barrier_bps: float | None = None,
    multiplier: float = 2.0,
    horizon: int = 12,
) -> pl.DataFrame:
    """Add triple barrier labels to an hourly DataFrame.

    Args:
        df: Polars DataFrame with columns [bucket, mid, bid, ask, ...]
        symbol: FX pair name (e.g., "EURUSD")
        cost_bps: Round-trip cost in basis points. Uses DEFAULT_COST_BPS if None.
        barrier_bps: Fixed barrier width in basis points. If None, computed as
                     max(5.0, cost_bps * multiplier).  5 bps is a minimum
                     economically-meaningful excursion for hourly FX.
        multiplier: Deprecated in favour of explicit barrier_bps.  If barrier_bps
                    is not provided, barrier = max(5.0, cost_bps * multiplier).
        horizon: Max holding period in hours.

    Returns:
        DataFrame with added columns: tb_label, tb_horizon, tb_barrier_bps.
    """
    if cost_bps is None:
        cost_bps = DEFAULT_COST_BPS.get(symbol, 0.80)

    if barrier_bps is None:
        # Minimum 5 bps — anything smaller is noise on hourly FX
        barrier_bps = max(5.0, cost_bps * multiplier)

    mids = df["mid"].to_numpy()
    bids = df["bid"].to_numpy()
    asks = df["ask"].to_numpy()
    n = len(mids)

    # barrier_delta in price terms
    barrier_deltas = mids * barrier_bps / 10_000.0

    labels = np.zeros(n, dtype=np.int8)
    horizons = np.zeros(n, dtype=np.int16)

    max_i = n - horizon - 1
    for i in range(max_i):
        labels[i], horizons[i] = _label_bar(
            mids, bids, asks, i, horizon, barrier_deltas[i], 1.0
        )

    labels[max_i:] = 0
    horizons[max_i:] = horizon

    return df.with_columns(
        pl.Series("tb_label", labels),
        pl.Series("tb_horizon", horizons),
        pl.lit(barrier_bps).alias("tb_barrier_bps"),
    )


def label_summary(df: pl.DataFrame) -> dict:
    """Return summary statistics of triple barrier labels."""
    labels = df["tb_label"].to_numpy()
    total = len(labels)
    n_pos = int((labels == 1).sum())
    n_neg = int((labels == -1).sum())
    n_zero = int((labels == 0).sum())
    return {
        "total": total,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "n_zero": n_zero,
        "pct_pos": round(n_pos / total * 100, 2),
        "pct_neg": round(n_neg / total * 100, 2),
        "pct_zero": round(n_zero / total * 100, 2),
        "avg_horizon": round(df["tb_horizon"].mean(), 2),
    }


if __name__ == "__main__":
    # Quick smoke test on EURUSD
    df = pl.read_parquet("data/tick_bars/EURUSD_1h_flow.parquet")

    for h in [6, 12, 24]:
        for mult in [1.0, 2.0]:
            labeled = label_hourly(df, "EURUSD", horizon=h, multiplier=mult)
            summary = label_summary(labeled)
            print(
                f"H={h:2d}h  mult={mult:.1f}  pos={summary['pct_pos']:5.2f}%  "
                f"neg={summary['pct_neg']:5.2f}%  zero={summary['pct_zero']:5.2f}%  "
                f"avg_horizon={summary['avg_horizon']:.1f}"
            )

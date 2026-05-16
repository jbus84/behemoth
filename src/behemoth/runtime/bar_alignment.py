"""Fixed-tick bar alignment utilities shared by runtime tick ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.behemoth.core.features import pip_size
from src.behemoth.core.schemas import IncomingTick, IncomingTickBar


@dataclass(frozen=True)
class BarAlignmentResult:
    bars: list[IncomingTickBar]
    remainder: list[IncomingTick]


class BarBoundaryContract(Protocol):
    """Contract for turning ordered ticks into completed bars and remainder."""

    def align(
        self,
        ticks: list[IncomingTick],
        *,
        symbol: str,
        bar_ticks: int,
    ) -> BarAlignmentResult:
        ...


class TickCountBarBoundary:
    """Fixed tick-count bar boundary adapter."""

    def align(
        self,
        ticks: list[IncomingTick],
        *,
        symbol: str,
        bar_ticks: int,
    ) -> BarAlignmentResult:
        size = int(bar_ticks)
        if size <= 0:
            raise ValueError("bar_ticks must be > 0")
        completed: list[IncomingTickBar] = []
        cursor = 0
        prev_close_bid: float | None = None
        while cursor + size <= len(ticks):
            chunk = ticks[cursor : cursor + size]
            completed.append(
                _build_bar(
                    chunk,
                    symbol=symbol.upper(),
                    bar_ticks=size,
                    prev_close_bid=prev_close_bid,
                )
            )
            prev_close_bid = float(chunk[-1].bid)
            cursor += size
        return BarAlignmentResult(bars=completed, remainder=ticks[cursor:])


class BarAlignmentService:
    """Build completed fixed-tick bars and return unconsumed remainder ticks."""

    def __init__(self, boundary: BarBoundaryContract | None = None) -> None:
        self._boundary = boundary or TickCountBarBoundary()

    def align_ticks(
        self,
        ticks: list[IncomingTick],
        *,
        symbol: str,
        bar_ticks: int,
    ) -> BarAlignmentResult:
        return self._boundary.align(ticks, symbol=symbol, bar_ticks=bar_ticks)


def _build_bar(
    ticks: list[IncomingTick],
    *,
    symbol: str,
    bar_ticks: int,
    prev_close_bid: float | None = None,
) -> IncomingTickBar:
    """Build a single bar from exactly ``bar_ticks`` ticks."""
    prices = [float(t.bid) for t in ticks]
    spreads = [float(t.ask - t.bid) for t in ticks]
    asks = [float(t.ask) for t in ticks]

    open_price, close_price, high_price, low_price, spread_mean = _compute_price_stats(prices, spreads)
    hl_first, hl_pos_frac = _compute_microstructure(prices, high_price, low_price, bar_ticks)

    if prev_close_bid is not None:
        if close_price > prev_close_bid:
            bar_return_sign = 1.0
        elif close_price < prev_close_bid:
            bar_return_sign = -1.0
        else:
            bar_return_sign = 0.0
    else:
        bar_return_sign = 0.0

    tick_burst = float(bar_ticks)

    if len(prices) >= 2:
        quote_revisions = float(
            sum(1 for i in range(1, len(prices)) if prices[i] != prices[i - 1])
        )
    else:
        quote_revisions = 0.0

    pip = pip_size(symbol)
    range_val = high_price - low_price
    intra_bar_momentum = hl_first * range_val / pip

    return IncomingTickBar(
        symbol=symbol,
        bar_ticks=bar_ticks,
        timestamp=ticks[0].timestamp,
        close_ts=ticks[-1].timestamp,
        open_bid=open_price,
        high_bid=high_price,
        low_bid=low_price,
        close_bid=close_price,
        spread=spread_mean,
        tick_volume=float(bar_ticks),
        hl_first=hl_first,
        hl_pos_frac=hl_pos_frac,
        high_ask=max(asks),
        close_ask=asks[-1],
        bar_return_sign=bar_return_sign,
        tick_burst=tick_burst,
        quote_revisions=quote_revisions,
        intra_bar_momentum=intra_bar_momentum,
    )


def _compute_microstructure(
    prices: list[float], high_price: float, low_price: float, bar_ticks: int
) -> tuple[float, float]:
    """Compute the microstructural sequence makers for a bar."""
    high_pos = prices.index(high_price)
    low_pos = prices.index(low_price)

    if high_pos < low_pos:
        hl_first = 1.0
    elif high_pos > low_pos:
        hl_first = -1.0
    else:
        hl_first = 0.0

    hl_pos_frac = (low_pos - high_pos) / max(1, bar_ticks - 1)
    return hl_first, hl_pos_frac


def _compute_price_stats(prices: list[float], spreads: list[float]) -> tuple[float, float, float, float, float]:
    """Compute basic OHLC and spread statistics from a tick window."""
    return (
        prices[0],
        prices[-1],
        max(prices),
        min(prices),
        sum(spreads) / len(spreads),
    )

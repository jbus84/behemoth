"""Real-time tick-to-bar aggregator.

Converts raw ``IncomingTick`` objects into ``IncomingTickBar`` objects
using the same fixed-tick-count logic as ``build_global_tick_bars.py``.

Each symbol maintains its own buffer.  When the buffer reaches
``bar_ticks`` ticks, a completed bar is emitted with:
- OHLC from mid prices (bid+ask)/2
- spread = mean(ask-bid) over the bar
- hl_first, hl_pos_frac matching the Polars reference implementation
- tick_volume = bar_ticks
"""

from __future__ import annotations

from collections import defaultdict

from src.behemoth.core.schemas import IncomingTick, IncomingTickBar


class TickAggregator:
    """Stateful tick-to-bar aggregator, one buffer per symbol.

    Parameters
    ----------
    bar_ticks : int
        Number of ticks per bar (default 100, matching research pipeline).
    """

    def __init__(self, bar_ticks: int = 100) -> None:
        self.bar_ticks = int(bar_ticks)
        self._buffers: dict[str, list[IncomingTick]] = defaultdict(list)

    def add_ticks(self, ticks: list[IncomingTick]) -> list[IncomingTickBar]:
        """Ingest ticks and return any completed bars.

        Ticks may span multiple symbols; each symbol's buffer is independent.
        """
        # Group ticks by symbol, preserving order within each group
        by_symbol: dict[str, list[IncomingTick]] = defaultdict(list)
        for t in ticks:
            by_symbol[t.symbol.upper()].append(t)

        completed: list[IncomingTickBar] = []
        for sym, sym_ticks in by_symbol.items():
            self._buffers[sym].extend(sym_ticks)
            buf = self._buffers[sym]

            while len(buf) >= self.bar_ticks:
                chunk = buf[: self.bar_ticks]
                bar = _build_bar(chunk, symbol=sym, bar_ticks=self.bar_ticks)
                completed.append(bar)
                buf = buf[self.bar_ticks :]

            self._buffers[sym] = buf

        return completed

    def remainder_count(self, symbol: str) -> int:
        """Return the number of buffered ticks not yet forming a bar."""
        return len(self._buffers.get(symbol.upper(), []))

    def latest_bid(self, symbol: str) -> float | None:
        """Return the bid price of the most recently received tick, or None if no ticks buffered."""
        buf = self._buffers.get(symbol.upper(), [])
        return float(buf[-1].bid) if buf else None


def _build_bar(
    ticks: list[IncomingTick],
    *,
    symbol: str,
    bar_ticks: int,
) -> IncomingTickBar:
    """Build a single bar from exactly ``bar_ticks`` ticks."""
    # Research reference (build_global_tick_bars.py) defaults to price_source="bid"
    prices = [float(t.bid) for t in ticks]
    spreads = [float(t.ask - t.bid) for t in ticks]

    open_price, close_price, high_price, low_price, spread_mean = _compute_price_stats(prices, spreads)

    hl_first, hl_pos_frac = _compute_microstructure(prices, high_price, low_price, bar_ticks)

    return IncomingTickBar(
        symbol=symbol,
        bar_ticks=bar_ticks,
        timestamp=ticks[0].timestamp,
        close_ts=ticks[-1].timestamp,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        spread=spread_mean,
        tick_volume=float(bar_ticks),
        hl_first=hl_first,
        hl_pos_frac=hl_pos_frac,
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

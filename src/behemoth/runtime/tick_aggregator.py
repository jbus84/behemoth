"""Real-time tick-to-bar aggregator.

Converts raw ``IncomingTick`` objects into ``IncomingTickBar`` objects
using the same fixed-tick-count logic as ``build_global_tick_bars.py``.

Each symbol maintains its own buffer.  When the buffer reaches
``bar_ticks`` ticks, a completed bar is emitted with:
- OHLC from bid prices
- spread = mean(ask-bid) over the bar
- hl_first, hl_pos_frac matching the Polars reference implementation
- tick_volume = bar_ticks
"""

from __future__ import annotations

from collections import defaultdict

from src.behemoth.core.schemas import IncomingTick, IncomingTickBar
from src.behemoth.runtime.bar_alignment import BarAlignmentService


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
        self._alignment = BarAlignmentService()

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
            aligned = self._alignment.align_ticks(buf, symbol=sym, bar_ticks=self.bar_ticks)
            completed.extend(aligned.bars)
            self._buffers[sym] = aligned.remainder

        return completed

    def remainder_count(self, symbol: str) -> int:
        """Return the number of buffered ticks not yet forming a bar."""
        return len(self._buffers.get(symbol.upper(), []))

    def latest_bid(self, symbol: str) -> float | None:
        """Return the bid price of the most recently received tick, or None if no ticks buffered."""
        buf = self._buffers.get(symbol.upper(), [])
        return float(buf[-1].bid) if buf else None

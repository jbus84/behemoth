"""Causal streaming replay of the raw bid/ask tick stream for one symbol-day.

`TickReplay` is the only place that touches the canonical feed. It loads a UTC time
window once, then yields `Tick` objects strictly in arrival order. It never exposes a
future row to a consumer, which is what makes look-ahead structurally impossible (the
engine sees tick *i* only after ticks 0..i-1). See `tests/era_tick/test_tick_replay.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from scripts.canonical_tick_feed import DEFAULT_DUKASCOPY_ROOT, load_ticks_window
from scripts.era_tick import pip_size


@dataclass(frozen=True, slots=True)
class Tick:
    """A single quote. `dt` is seconds since the previous tick (0.0 for the first)."""

    i: int
    ts: pd.Timestamp
    bid: float
    ask: float
    dt: float

    @property
    def mid(self) -> float:
        return 0.5 * (self.bid + self.ask)

    @property
    def spread(self) -> float:
        return self.ask - self.bid


class TickReplay:
    """Iterable replay of `[timestamp, bid, ask]` for one symbol over a time window."""

    def __init__(self, symbol: str, frame: pd.DataFrame) -> None:
        self.symbol = str(symbol).upper()
        self.pip = pip_size(self.symbol)
        self._frame = frame.reset_index(drop=True)

    @classmethod
    def load(
        cls,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        *,
        root: Path = DEFAULT_DUKASCOPY_ROOT,
    ) -> TickReplay:
        """Load all ticks for `symbol` in `[start, end)` (UTC) from the canonical feed."""
        frame = load_ticks_window(symbol=symbol, root=root, start=start, end=end)
        return cls(symbol, frame)

    @classmethod
    def for_day(
        cls,
        symbol: str,
        date: str,
        *,
        start_hhmm: str = "07:00",
        end_hhmm: str = "17:00",
        root: Path = DEFAULT_DUKASCOPY_ROOT,
    ) -> TickReplay:
        """Convenience: one calendar day, default London/NY overlap 07:00-17:00 UTC."""
        start = pd.Timestamp(f"{date} {start_hhmm}", tz="UTC")
        end = pd.Timestamp(f"{date} {end_hhmm}", tz="UTC")
        return cls.load(symbol, start, end, root=root)

    def __len__(self) -> int:
        return len(self._frame)

    @property
    def spread_pips_series(self) -> pd.Series:
        """Per-tick spread in pips (diagnostics / cost overlays). Not used for decisions."""
        return (self._frame["ask"] - self._frame["bid"]) / self.pip

    @property
    def mids(self) -> pd.Series:
        """Per-tick mid price (diagnostics / regime scoring over the whole window)."""
        return 0.5 * (self._frame["bid"] + self._frame["ask"])

    def __iter__(self) -> Iterator[Tick]:
        prev_ts: pd.Timestamp | None = None
        for i, bid, ask, ts in zip(
            range(len(self._frame)),
            self._frame["bid"].to_numpy(),
            self._frame["ask"].to_numpy(),
            self._frame["timestamp"],
        ):
            dt = 0.0 if prev_ts is None else max(0.0, (ts - prev_ts).total_seconds())
            prev_ts = ts
            yield Tick(i=i, ts=ts, bid=float(bid), ask=float(ask), dt=dt)

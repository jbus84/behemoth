"""Tick-exact fill model.

At tick level a market order does not execute at the mid. It crosses the spread: a buy
pays the ask, a sell receives the bid, at the exact tick the decision is acted on. The
spread is therefore paid where it is touched, not as a bar-average — which is the whole
point of doing this tick-by-tick (cf. the bar pipeline that hides adverse selection in a
bar mean).

`retail_markup_pips` overlays a broker markup *on top of* the raw Dukascopy spread to
model a retail venue (e.g. IG spread betting), split half per side. It is a round-trip
figure: 0.0 = Dukascopy-truth (best case), ~0.5 = a realistic retail scenario.

A `maker` mode (limit at the touch, no spread paid) is provided but OFF by default —
maker fills are the known mirage here (adverse selection turned a +1.17p OHLC edge into
-0.74p tick-exact), so they must be earned with a tick-exact queue model, not assumed.
"""

from __future__ import annotations

from dataclasses import dataclass

from scripts.era_tick.tick_replay import Tick


@dataclass(frozen=True, slots=True)
class FillModel:
    pip: float
    retail_markup_pips: float = 0.0
    maker: bool = False

    @property
    def _half_markup(self) -> float:
        return 0.5 * self.retail_markup_pips * self.pip

    def buy_price(self, tick: Tick) -> float:
        """Price paid to go long (or to close a short)."""
        if self.maker:
            return tick.bid  # optimistic: filled at the near touch, no spread paid
        return tick.ask + self._half_markup

    def sell_price(self, tick: Tick) -> float:
        """Price received to go short (or to close a long)."""
        if self.maker:
            return tick.ask
        return tick.bid - self._half_markup

    def round_trip_cost_pips(self, tick: Tick) -> float:
        """Implied round-trip cost in pips at this tick's quote (spread + markup)."""
        if self.maker:
            return 0.0
        return tick.spread / self.pip + self.retail_markup_pips

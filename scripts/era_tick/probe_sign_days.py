"""Diagnostic probe: characterise intrabar structure across days and entry sign.

The Day-1 fade showed NEGATIVE gross. This probe asks the cheaper, more fundamental
question before we invest in an ERA search: is there *any* exploitable intrabar
structure? We run the same machinery on several days under two mirror-image policies:

- FADE     : short an up-extension that is rolling over (the Day-1 baseline).
- MOMENTUM : the exact opposite — go *with* the extension.

If FADE gross < 0 and MOMENTUM gross > 0 (or vice-versa) consistently, there is signed
structure worth an ERA search. If both hover at/under zero, the intrabar move is noise at
this scale and no policy search will rescue it. Gross is reported before cost so the
verdict is about signal existence, not execution.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from scripts.era_tick.engine import TickEngine
from scripts.era_tick.fill_model import FillModel
from scripts.era_tick.metrics import summarize
from scripts.era_tick.policy import Action, TickState
from scripts.era_tick.regime import Regime
from scripts.era_tick.tick_replay import TickReplay

DAYS = [
    "2024-02-13",  # US CPI
    "2024-03-12",  # US CPI
    "2024-04-10",  # US CPI (Day-1 sample)
    "2024-05-15",  # US CPI
    "2024-06-12",  # US CPI + FOMC
]


@dataclass(frozen=True, slots=True)
class _SignPolicy:
    """Fade or follow micro-extensions; managed exits identical to the baseline."""

    follow: bool  # False = fade, True = momentum
    enter_z: float = 2.0
    take_profit_pips: float = 2.0
    stop_pips: float = 1.5
    max_hold_ticks: int = 400
    max_spread_pips: float = 0.5

    def decide(self, state: TickState) -> Action:
        if state.position == 0:
            return self._entry(state)
        return self._exit(state)

    def _entry(self, state: TickState) -> Action:
        if state.regime is not Regime.REVERT or state.spread_pips > self.max_spread_pips:
            return Action.NONE
        up = state.residual_z >= self.enter_z and state.drift_hat < 0.0
        down = state.residual_z <= -self.enter_z and state.drift_hat > 0.0
        if up:
            return Action.ENTER_LONG if self.follow else Action.ENTER_SHORT
        if down:
            return Action.ENTER_SHORT if self.follow else Action.ENTER_LONG
        return Action.NONE

    def _exit(self, state: TickState) -> Action:
        if state.unrealized_pips >= self.take_profit_pips:
            return Action.EXIT
        if state.unrealized_pips <= -self.stop_pips:
            return Action.EXIT
        if state.hold_ticks >= self.max_hold_ticks:
            return Action.EXIT
        return Action.NONE


def _run(symbol: str, day: str, follow: bool) -> dict:
    replay = TickReplay.for_day(symbol, day)
    if len(replay) == 0:
        return {}
    eng = TickEngine(_SignPolicy(follow=follow), FillModel(pip=replay.pip), record_trace=False)
    s = summarize(eng.run(replay).trades)
    return {
        "day": day,
        "policy": "momentum" if follow else "fade",
        "n": s.n_trades,
        "gross/trade": round(s.gross_pips_per_trade, 4),
        "net/trade": round(s.net_pips_per_trade, 4),
        "hit": round(s.hit_rate, 3),
    }


def main() -> None:
    symbol = "EURUSD"
    rows = [r for day in DAYS for follow in (False, True) if (r := _run(symbol, day, follow))]
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print("\n--- mean gross/trade by policy (before cost) ---")
    print(df.groupby("policy")["gross/trade"].mean().round(4).to_string())


if __name__ == "__main__":
    main()

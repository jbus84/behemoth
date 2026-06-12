"""Can we capture the fade's huge loss by inverting it?

The router run showed fade net = −3530p over ~109 afternoons. If fade loses by being on the
WRONG SIDE (negative gross), its mirror captures that. If it loses because it OVERTRADES (the
loss is just round-trip cost, gross ~0), inverting pays the same cost and gains nothing —
`inverted_net = -original_net - 2*cost`, which is only positive when cost < |net|/... i.e.
when the loss is NOT cost-dominated. This decides it empirically:

  1. Run fade over the broad day set; decompose aggregate gross vs cost vs net.
  2. Pure sign-flip (interpretation A): inverted_net = -net - 2*cost (derived; exits flip too).
  3. Inverted-entry fade (interpretation B): flip only the entry signal, keep risk exits, and
     actually run it — a genuinely different strategy (momentum-style entry, fade's tight exits).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from scripts.era_tick.engine import TickEngine
from scripts.era_tick.fill_model import FillModel
from scripts.era_tick.metrics import summarize
from scripts.era_tick.policy import Action, NaiveFadePolicy, TickPolicy, TickState
from scripts.era_tick.tick_replay import TickReplay


@dataclass(frozen=True, slots=True)
class InvertedEntry:
    """Wrap a policy and flip only its entry direction (keep its exits)."""

    inner: TickPolicy

    def decide(self, state: TickState) -> Action:
        a = self.inner.decide(state)
        if a is Action.ENTER_LONG:
            return Action.ENTER_SHORT
        if a is Action.ENTER_SHORT:
            return Action.ENTER_LONG
        return a


def _totals(symbol: str, day: str, policy) -> dict | None:
    replay = TickReplay.for_day(symbol, day, start_hhmm="09:00", end_hhmm="17:00")
    if len(replay) == 0:
        return None
    eng = TickEngine(policy, FillModel(pip=replay.pip), record_trace=False)
    s = summarize(eng.run(replay).trades)
    n = s.n_trades
    return {
        "n": n,
        "gross_total": s.gross_pips_per_trade * n,
        "cost_total": s.cost_pips_per_trade * n,
        "net_total": s.total_net_pips,
    }


def _agg(symbol: str, days: list[str], make_policy) -> dict:
    rows = [t for d in days if (t := _totals(symbol, d, make_policy()))]
    df = pd.DataFrame(rows)
    return {
        "days": len(df),
        "n": int(df["n"].sum()),
        "gross_total": round(df["gross_total"].sum(), 1),
        "cost_total": round(df["cost_total"].sum(), 1),
        "net_total": round(df["net_total"].sum(), 1),
    }


def main() -> None:
    symbol = "EURUSD"
    days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-03-01", "2024-07-31")]

    fade = _agg(symbol, days, NaiveFadePolicy)
    print("FADE (original):", fade)

    # Interpretation A: pure sign-flip. P&L mid-move negates; spread still paid both ways.
    inv_a = round(-fade["net_total"] - 2 * fade["cost_total"], 1)
    print(f"\nA) pure sign-flip  inverted_net = -net - 2*cost = {inv_a}p")
    print("   (positive only if fade's loss is wrong-side gross, not overtrading cost)")

    # Interpretation B: flip only the entry, keep the exits — run it for real.
    inv_b = _agg(symbol, days, lambda: InvertedEntry(NaiveFadePolicy()))
    print("\nB) inverted-entry (real run):", inv_b)

    print("\n--- read ---")
    cost_dominated = abs(fade["gross_total"]) < 0.5 * abs(fade["net_total"])
    if cost_dominated:
        print("  Fade loss is COST-DOMINATED (gross ~0): inversion is a wash. Dead end.")
    else:
        print("  Fade has real WRONG-SIDE gross: inversion may capture it. Worth pursuing.")


if __name__ == "__main__":
    main()

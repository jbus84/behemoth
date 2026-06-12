"""Experiment: be selective. Only trade when the filter is confident, then ride.

The Day-1 fade and the first momentum probe both traded ~constantly (700+/day, ~10-tick
holds) for a tiny per-trade mean. The fix this tests: enter ONLY when the Kalman filter is
statistically confident a real trend exists (|drift_t| above a threshold) AND the tape is
in the directional (DRIFT) regime, enter *with* the trend, and then RIDE until that
confidence decays (|drift_t| falls, the drift flips, or the regime breaks) — cutting losers
with a stop but letting winners run. The momentum payoff is "cut fast, ride winners".

We scan the entry-confidence threshold on two day populations — high-trend US-data days
vs ordinary days — and report, before and after cost, whether selectivity concentrates
trades into a tail whose gross clears the wall. The event/ordinary split is the headline:
ride-momentum clears raw cost on trend days and bleeds on chop, so the edge is
regime-conditional, not constant. Gross is mid-to-mid; cost is raw Dukascopy
(spread + commission + slippage ~0.22p RT).
"""

from __future__ import annotations

import pandas as pd

from scripts.era_tick.engine import TickEngine
from scripts.era_tick.fill_model import FillModel
from scripts.era_tick.metrics import summarize
from scripts.era_tick.policy import ConfidentMomentumPolicy
from scripts.era_tick.tick_replay import TickReplay

# Two deliberately different day populations: high-trend US-data days vs ordinary days.
# The contrast is the whole point — momentum looks great on trend days and bleeds on chop.
DAY_SETS = {
    "event": ["2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15", "2024-06-12"],
    "ordinary": [
        "2024-04-16",
        "2024-04-17",
        "2024-04-23",
        "2024-04-24",
        "2024-05-21",
        "2024-05-22",
        "2024-05-28",
        "2024-06-18",
        "2024-06-25",
        "2024-07-09",
    ],
}
ENTER_T = [3.0, 5.0]
RAW_COST_PIPS = 0.22  # approx round-trip raw Dukascopy cost for context


def _run(symbol: str, day: str, enter_t: float, day_set: str) -> dict:
    replay = TickReplay.for_day(symbol, day)
    if len(replay) == 0:
        return {}
    policy = ConfidentMomentumPolicy(enter_t=enter_t)
    eng = TickEngine(policy, FillModel(pip=replay.pip), record_trace=False)
    s = summarize(eng.run(replay).trades)
    return {
        "day_set": day_set,
        "enter_t": enter_t,
        "day": day,
        "n": s.n_trades,
        "gross/trade": round(s.gross_pips_per_trade, 3),
        "net/trade": round(s.net_pips_per_trade, 3),
        "hit": round(s.hit_rate, 3),
        "avg_hold": round(s.avg_hold_ticks, 0),
    }


def main() -> None:
    symbol = "EURUSD"
    rows = [
        r
        for day_set, days in DAY_SETS.items()
        for et in ENTER_T
        for day in days
        if (r := _run(symbol, day, et, day_set))
    ]
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))

    print("\n--- aggregate by day_set x enter_t (mean over days) ---")
    agg = df.groupby(["day_set", "enter_t"]).agg(
        trades_per_day=("n", "mean"),
        gross_per_trade=("gross/trade", "mean"),
        net_per_trade=("net/trade", "mean"),
        hit=("hit", "mean"),
        avg_hold=("avg_hold", "mean"),
    )
    agg["gross/cost"] = (agg["gross_per_trade"] / RAW_COST_PIPS).round(2)
    print(agg.round(3).to_string())
    print(
        f"\n(raw round-trip cost reference ~{RAW_COST_PIPS}p; gross must clear it AND be net-positive)"
    )


if __name__ == "__main__":
    main()

"""Cross-symbol probe: is the momentum signal juicier on a more trending pair?

EURUSD is the most range-bound major, so it is arguably the worst case for a continuation
edge. This runs the confident-momentum policy unchanged across all six majors on a common set
of days and reports the only thing that matters — the gross-vs-cost ratio per trade — plus the
mean spread (the cost driver). If a wider-range pair (GBPUSD/USDJPY/AUD/CAD) lifts gross/cost,
that is where the ERA search should be pointed.
"""

from __future__ import annotations

import pandas as pd

from scripts.era_tick.engine import TickEngine
from scripts.era_tick.fill_model import FillModel
from scripts.era_tick.metrics import summarize
from scripts.era_tick.policy import ConfidentMomentumPolicy
from scripts.era_tick.tick_replay import TickReplay

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"]
# A common set of ordinary weekdays (mix of months, avoid concentrating on event days).
DAYS = [
    "2024-04-16",
    "2024-04-23",
    "2024-05-07",
    "2024-05-21",
    "2024-06-04",
    "2024-06-18",
    "2024-07-02",
    "2024-07-09",
    "2024-07-16",
    "2024-07-23",
]


def _symbol_row(symbol: str) -> dict | None:
    n_days = 0
    grosses, costs, nets, spreads, ntr = [], [], [], [], []
    for day in DAYS:
        replay = TickReplay.for_day(symbol, day)
        if len(replay) == 0:
            continue
        n_days += 1
        spreads.append(float(replay.spread_pips_series.mean()))
        eng = TickEngine(
            ConfidentMomentumPolicy(enter_t=3.0), FillModel(pip=replay.pip), record_trace=False
        )
        s = summarize(eng.run(replay).trades)
        if s.n_trades == 0:
            continue
        grosses.append(s.gross_pips_per_trade)
        costs.append(s.cost_pips_per_trade)
        nets.append(s.net_pips_per_trade)
        ntr.append(s.n_trades)
    if not grosses:
        return None
    g = sum(grosses) / len(grosses)
    c = sum(costs) / len(costs)
    return {
        "symbol": symbol,
        "days": n_days,
        "mean_spread_pips": round(sum(spreads) / len(spreads), 3),
        "trades/day": round(sum(ntr) / len(ntr), 1),
        "gross/trade": round(g, 4),
        "cost/trade": round(c, 4),
        "net/trade": round(sum(nets) / len(nets), 4),
        "gross/cost": round(g / c, 2) if c > 0 else float("nan"),
    }


def main() -> None:
    rows = [r for s in SYMBOLS if (r := _symbol_row(s))]
    df = pd.DataFrame(rows).sort_values("gross/cost", ascending=False)
    print(df.to_string(index=False))
    print("\ngross/cost > 1 means the per-trade continuation edge clears its own cost.")


if __name__ == "__main__":
    main()

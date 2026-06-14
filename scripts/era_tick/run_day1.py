"""Day-1 prototype runner.

Replays one symbol-day tick-by-tick through the naive fade policy with tick-exact fills,
prints the gross / cost / net / significance table under both the raw Dukascopy spread and
a retail-markup scenario, writes the trade log (CSV) and the diagnostic plot, and states
the go/no-go verdict: is gross pips/trade > 2x the round-trip cost?

Usage:
    python -m scripts.era_tick.run_day1 --symbol EURUSD --date 2024-04-10
    python -m scripts.era_tick.run_day1 --symbol EURUSD --date 2024-04-10 \
        --start 07:00 --end 17:00 --retail-markup-pips 0.5
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.era_tick.engine import TickEngine
from scripts.era_tick.fill_model import FillModel
from scripts.era_tick.metrics import Summary, reprice_with_markup, summarize, trades_frame
from scripts.era_tick.policy import NaiveFadePolicy
from scripts.era_tick.tick_replay import TickReplay
from scripts.era_tick.viz import plot_run

_OUT = Path("data/era_tick")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tick-by-tick Day-1 fade prototype")
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--date", required=True, help="UTC calendar day, YYYY-MM-DD")
    p.add_argument("--start", default="07:00", help="window start HH:MM UTC")
    p.add_argument("--end", default="17:00", help="window end HH:MM UTC")
    p.add_argument(
        "--retail-markup-pips",
        type=float,
        default=0.5,
        help="extra round-trip markup for the retail-cost scenario",
    )
    p.add_argument("--enter-z", type=float, default=2.0)
    p.add_argument("--take-profit-pips", type=float, default=2.0)
    p.add_argument("--stop-pips", type=float, default=1.5)
    p.add_argument("--no-plot", action="store_true")
    return p.parse_args()


def _verdict(raw: Summary) -> str:
    if raw.n_trades == 0:
        return "NO-GO: zero trades — policy never triggered on this day."
    rt_cost = raw.cost_pips_per_trade
    gross = raw.gross_pips_per_trade
    ratio = gross / rt_cost if rt_cost > 0 else float("inf")
    gate = gross > 2.0 * rt_cost
    tag = "GO" if gate else "NO-GO"
    return (
        f"{tag}: gross/trade {gross:+.3f}p vs 2x round-trip cost "
        f"{2 * rt_cost:.3f}p (gross/cost = {ratio:.2f}x). "
        f"net/trade {raw.net_pips_per_trade:+.3f}p over {raw.n_trades} trades, "
        f"t={raw.t_stat:.2f}."
    )


def main() -> None:
    args = _parse_args()
    replay = TickReplay.for_day(args.symbol, args.date, start_hhmm=args.start, end_hhmm=args.end)
    print(f"{args.symbol} {args.date} {args.start}-{args.end} UTC: {len(replay):,} ticks")
    if len(replay) == 0:
        print("No ticks in window (weekend/holiday?). Nothing to do.")
        return

    policy = NaiveFadePolicy(
        enter_z=args.enter_z,
        take_profit_pips=args.take_profit_pips,
        stop_pips=args.stop_pips,
    )
    fill = FillModel(pip=replay.pip, retail_markup_pips=0.0)
    engine = TickEngine(policy, fill, record_trace=not args.no_plot)
    result = engine.run(replay)

    raw = summarize(result.trades)
    retail = reprice_with_markup(result.trades, args.retail_markup_pips)
    table = pd.DataFrame(
        [
            raw.as_row("raw_dukascopy"),
            retail.as_row(f"retail_+{args.retail_markup_pips}p"),
        ]
    )
    print("\n" + table.to_string(index=False))
    print("\nVERDICT (raw spread): " + _verdict(raw))

    _OUT.mkdir(parents=True, exist_ok=True)
    tag = f"{args.symbol}_{args.date}"
    if result.trades:
        trades_frame(result.trades).to_csv(_OUT / f"trades_{tag}.csv", index=False)
        print(f"trade log -> {_OUT / f'trades_{tag}.csv'}")
    if not args.no_plot and result.trace:
        path = plot_run(result, _OUT / "plots" / f"{tag}.png", title=f"{args.symbol} {args.date}")
        print(f"plot      -> {path}")


if __name__ == "__main__":
    main()

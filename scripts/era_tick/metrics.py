"""Trade-log metrics — gross / cost / significance kept separate.

Following the house rule (never trust a net mean): we report gross (mid-to-mid) edge,
the cost actually paid, and the net separately, plus a t-stat and win rate so a near-zero
net is not mistaken for signal. `score_frame` is the adapter the ERA RunSpec will call:
it returns one net-pips-per-trade row per trade so the existing cost-aware scorer can
rank tick policies exactly as it ranks bar programs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from scripts.era_tick.engine import Trade


@dataclass(frozen=True, slots=True)
class Summary:
    n_trades: int
    gross_pips_per_trade: float
    cost_pips_per_trade: float
    net_pips_per_trade: float
    total_net_pips: float
    hit_rate: float
    t_stat: float
    avg_hold_ticks: float
    long_frac: float

    def as_row(self, label: str) -> dict:
        return {
            "scenario": label,
            "n": self.n_trades,
            "gross/trade": round(self.gross_pips_per_trade, 4),
            "cost/trade": round(self.cost_pips_per_trade, 4),
            "net/trade": round(self.net_pips_per_trade, 4),
            "total_net": round(self.total_net_pips, 2),
            "hit_rate": round(self.hit_rate, 3),
            "t_stat": round(self.t_stat, 2),
            "avg_hold": round(self.avg_hold_ticks, 1),
            "long_frac": round(self.long_frac, 2),
        }


def trades_frame(trades: list[Trade]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "direction": [t.direction for t in trades],
            "gross_pips": [t.gross_pips for t in trades],
            "cost_pips": [t.cost_pips for t in trades],
            "net_pips": [t.net_pips for t in trades],
            "hold_ticks": [t.hold_ticks for t in trades],
        }
    )


def summarize(trades: list[Trade]) -> Summary:
    if not trades:
        return Summary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    df = trades_frame(trades)
    net = df["net_pips"].to_numpy()
    n = len(net)
    sd = float(net.std(ddof=1)) if n > 1 else 0.0
    t_stat = float(net.mean() / (sd / np.sqrt(n))) if sd > 0.0 else 0.0
    return Summary(
        n_trades=n,
        gross_pips_per_trade=float(df["gross_pips"].mean()),
        cost_pips_per_trade=float(df["cost_pips"].mean()),
        net_pips_per_trade=float(net.mean()),
        total_net_pips=float(net.sum()),
        hit_rate=float((net > 0).mean()),
        t_stat=t_stat,
        avg_hold_ticks=float(df["hold_ticks"].mean()),
        long_frac=float((df["direction"] == 1).mean()),
    )


def reprice_with_markup(trades: list[Trade], extra_markup_pips: float) -> Summary:
    """Re-summarise as if an additional round-trip markup were charged per trade.

    Lets the runner show a retail-cost scenario without re-running the engine: gross and
    hold are unchanged; cost and net shift by `extra_markup_pips`.
    """
    if not trades or extra_markup_pips == 0.0:
        return summarize(trades)
    bumped = [
        replace(
            t,
            cost_pips=t.cost_pips + extra_markup_pips,
            net_pips=t.net_pips - extra_markup_pips,
        )
        for t in trades
    ]
    return summarize(bumped)


def score_frame(trades: list[Trade]) -> pd.DataFrame:
    """ERA adapter: one net-pips row per trade (column `net`) for the cost-aware scorer."""
    return pd.DataFrame({"net": [t.net_pips for t in trades]})

"""Adverse-selection stress-test: run smoothed system with p_fill < 1.0 and adv_bps > 0.

Tests whether the edge survives realistic maker execution.
"""
from __future__ import annotations

from itertools import product
from pathlib import Path

import pandas as pd

from scripts.research.crypto_flow_overlays import (
    cost_per_turn,
    drawdown_guard,
    momentum_stop,
)
from scripts.research.crypto_flow_overlays import (
    metrics as _metrics,
)
from scripts.research.crypto_flow_xs_broad import backtest

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"
H = 48


def run_net(perp: pd.DataFrame, w: int, h: int, k: int, years: tuple, fm: dict, signal: str = "flow6") -> pd.Series:
    r = backtest(perp, w, h, k, years, fm, signal=signal)
    net = r["gross"] - r["turn"] * cost_per_turn(fm) + r["fund_pnl"]
    idx = pd.DatetimeIndex(r["dates"]).tz_localize(None)
    return pd.Series(net, index=idx)


def metrics(s: pd.Series) -> dict:
    return _metrics(s, H)


def main() -> None:
    perp = pd.read_parquet(CACHE_PERP)
    perp = perp[(perp["dt"] >= "2020-01-01") & (perp["dt"] < "2025-06-01")]
    perp = perp.sort_values(["symbol", "dt"])
    bar_counts = perp.groupby("symbol").size()
    keep_syms = bar_counts[bar_counts >= 5000].index.tolist()
    perp = perp[perp["symbol"].isin(keep_syms)].copy()

    years = tuple(range(2020, 2026))

    # base retail fee model — realistic 0.2 bps maker rebate (NOT rebate==spread,
    # which would zero out trading cost). p_fill / adv are the stressed axes below.
    base_fm = {
        "name": "retail_maker",
        "spread_bps": 2.0,
        "maker_rebate_bps": 0.2,
        "taker_fee_bps": 5.0,
        "queue_pos": 0.0,
    }

    # grid: p_fill_base × adv_bps
    p_fills = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5]
    adv_bpss = [0.0, 0.3, 0.6, 1.0, 1.5, 2.0]

    print(f"{'p_fill':>6s} {'adv':>5s} {'baseline_sharpe':>15s} {'baseline_maxDD':>15s} {'baseline_final':>14s} {'smooth_sharpe':>13s} {'smooth_maxDD':>13s} {'smooth_final':>12s}")
    rows = []
    for p, adv in product(p_fills, adv_bpss):
        fm = {**base_fm, "p_fill_base": p, "adv_bps": adv}
        s = run_net(perp, 24, 48, 5, years, fm)
        m_base = metrics(s)
        s_smooth = momentum_stop(drawdown_guard(s), 3, -0.02, 0.5)
        m_smooth = metrics(s_smooth)
        rows.append((p, adv, m_base, m_smooth))
        print(f"{p:>6.1f} {adv:>5.1f} {m_base['sharpe']:+15.2f} {m_base['max_dd']*100:+15.1f}% {m_base['final']:>14.2f}x {m_smooth['sharpe']:+13.2f} {m_smooth['max_dd']*100:+13.1f}% {m_smooth['final']:>12.2f}x")

    # find break-even: where smooth_sharpe drops below 1.0 or final < 1.0
    break_even = None
    for p, adv, _m_base, m_smooth in rows:
        if m_smooth["sharpe"] < 1.0 or m_smooth["final"] < 1.0:
            break_even = (p, adv, m_smooth)
            break

    if break_even:
        print(f"\nBreak-even boundary: p_fill={break_even[0]}  adv={break_even[1]}bps  sharpe={break_even[2]['sharpe']:.2f}  final={break_even[2]['final']:.2f}x")
    else:
        print("\nEdge survives full grid — even p_fill=0.5 + adv=2.0bps is profitable")

    # write
    out = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_flow_adverse_selection.md"
    lines = [
        "# Adverse-selection stress-test (full history 2020-2025)\n\n",
        "Grid: p_fill_base × adv_bps on h48_k5 + combined overlay.\n\n",
        "| p_fill | adv | baseline Sharpe | baseline maxDD | baseline final | smooth Sharpe | smooth maxDD | smooth final |\n",
        "|--------|-----|-----------------|----------------|----------------|---------------|--------------|--------------|\n",
    ]
    for p, adv, m_base, m_smooth in rows:
        lines.append(
            f"| {p:.1f} | {adv:.1f} | {m_base['sharpe']:+.2f} | {m_base['max_dd']:.1%} | {m_base['final']:.2f}x | "
            f"{m_smooth['sharpe']:+.2f} | {m_smooth['max_dd']:.1%} | {m_smooth['final']:.2f}x |\n"
        )
    if break_even:
        lines.append(f"\n**Break-even boundary**: p_fill={break_even[0]}  adv={break_even[1]}bps\n")
    else:
        lines.append("\n**Edge survives full grid** — even p_fill=0.5 + adv=2.0bps is profitable.\n")
    out.write_text("".join(lines))
    print(f"\nWrote → {out}")


if __name__ == "__main__":
    main()

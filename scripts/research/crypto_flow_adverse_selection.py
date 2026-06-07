"""Adverse-selection stress-test: run smoothed system with p_fill < 1.0 and adv_bps > 0.

Tests whether the edge survives realistic maker execution.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from itertools import product

from scripts.research.crypto_flow_xs_broad import backtest

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"


def run_net(perp: pd.DataFrame, w: int, h: int, k: int, years: tuple, fm: dict, signal: str = "flow6") -> pd.Series:
    r = backtest(perp, w, h, k, years, fm, signal=signal)
    spread = fm.get("spread_bps", 2.0) / 1e4
    rebate = fm.get("maker_rebate_bps", 2.0) / 1e4
    taker_fee = fm.get("taker_fee_bps", 5.0) / 1e4
    queue_pos = fm.get("queue_pos", 0.0)
    adv = fm.get("adv_bps", 0.0) / 1e4
    p_fill_base = fm.get("p_fill_base", 1.0)
    p_fill = max(0.05, p_fill_base * (1 - queue_pos))
    cost_per_turn = p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)
    net = r["gross"] - r["turn"] * cost_per_turn + r["fund_pnl"]
    idx = pd.DatetimeIndex(r["dates"]).tz_localize(None)
    return pd.Series(net, index=idx)


def overlay_guard(s: pd.Series, soft: float = -0.08, hard: float = -0.15, soft_scale: float = 0.25) -> pd.Series:
    cum = (1 + s).cumprod()
    scale = pd.Series(1.0, index=s.index)
    peak = cum.iloc[0]
    for i in range(len(cum)):
        peak = max(peak, cum.iloc[i])
        dd = (cum.iloc[i] - peak) / peak
        if dd <= hard:
            scale.iloc[i] = 0.0
        elif dd <= soft:
            scale.iloc[i] = soft_scale
    return s * scale


def overlay_mom_stop(s: pd.Series, window: int = 3, threshold: float = -0.02, scale: float = 0.5) -> pd.Series:
    cum_ret = (1 + s).cumprod()
    rolling_ret = cum_ret.pct_change(window).reindex(s.index).fillna(0)
    sc = pd.Series(1.0, index=s.index)
    sc[rolling_ret < threshold] = scale
    return s * sc


def metrics(s: pd.Series) -> dict:
    cum = (1 + s).cumprod()
    dd = (cum - cum.cummax()) / cum.cummax()
    return {
        "sharpe": s.mean() / s.std() * np.sqrt(365) if s.std() > 0 else 0.0,
        "max_dd": dd.min(),
        "final": cum.iloc[-1],
        "vol_ann": s.std() * np.sqrt(365),
    }


def main() -> None:
    perp = pd.read_parquet(CACHE_PERP)
    perp = perp[(perp["dt"] >= "2020-01-01") & (perp["dt"] < "2025-06-01")]
    perp = perp.sort_values(["symbol", "dt"])
    bar_counts = perp.groupby("symbol").size()
    keep_syms = bar_counts[bar_counts >= 5000].index.tolist()
    perp = perp[perp["symbol"].isin(keep_syms)].copy()

    years = tuple(range(2020, 2026))

    # base retail fee model
    base_fm = {
        "name": "retail_maker",
        "spread_bps": 2.0,
        "maker_rebate_bps": 2.0,
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
        s_smooth = overlay_mom_stop(overlay_guard(s), 3, -0.02, 0.5)
        m_smooth = metrics(s_smooth)
        rows.append((p, adv, m_base, m_smooth))
        print(f"{p:>6.1f} {adv:>5.1f} {m_base['sharpe']:+15.2f} {m_base['max_dd']*100:+15.1f}% {m_base['final']:>14.2f}x {m_smooth['sharpe']:+13.2f} {m_smooth['max_dd']*100:+13.1f}% {m_smooth['final']:>12.2f}x")

    # find break-even: where smooth_sharpe drops below 1.0 or final < 1.0
    break_even = None
    for p, adv, m_base, m_smooth in rows:
        if m_smooth["sharpe"] < 1.0 or m_smooth["final"] < 1.0:
            break_even = (p, adv, m_smooth)
            break

    if break_even:
        print(f"\nBreak-even boundary: p_fill={break_even[0]}  adv={break_even[1]}bps  sharpe={break_even[2]['sharpe']:.2f}  final={break_even[2]['final']:.2f}x")
    else:
        print(f"\nEdge survives full grid — even p_fill=0.5 + adv=2.0bps is profitable")

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

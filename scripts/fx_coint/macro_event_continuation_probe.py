"""Macro event continuation probe: post-NFP momentum on FX daily bars.

Opposite of the fade hypothesis: FX moves on NFP day PERSIST into Monday.
Uses causal expanding-window selectivity and real Razor cost.

Usage:
    uv run python scripts/fx_coint/macro_event_continuation_probe.py
"""
from __future__ import annotations

import calendar
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import spearmanr, ttest_1samp

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402

rsh.FREQ_MINUTES["1d"] = 1440

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF"]
COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89}
RNG = np.random.default_rng(0)


def cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def nfp_dates(start_year: int, end_year: int) -> list[date]:
    """First Friday of every month."""
    out = []
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            c = calendar.Calendar()
            fridays = [d for d in c.itermonthdates(year, month)
                       if d.weekday() == 4 and d.month == month]
            if fridays:
                out.append(fridays[0])
    return out


def load_daily(sym: str) -> pd.DataFrame:
    bars = rsh.build_freq_bars(
        pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
        "1d",
        session=(0, 24),
    )
    bars["ret_bps"] = np.log(bars["mid"]).diff() * 1e4
    return bars


def boot_ci(net: np.ndarray, buckets: np.ndarray, n_boot: int = 3000) -> tuple[float, float]:
    if len(net) < 3:
        return np.nan, np.nan
    s = pd.Series(net, index=pd.to_datetime(buckets).year)
    arrs = [g.to_numpy() for _, g in s.groupby(level=0)]
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = RNG.integers(0, len(arrs), len(arrs))
        means[b] = np.concatenate([arrs[i] for i in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def pos_years(net: np.ndarray, buckets: np.ndarray) -> tuple[int, int]:
    yr = pd.Series(net, index=pd.to_datetime(buckets).year).groupby(level=0).mean()
    return int((yr > 0).sum()), len(yr)


def line(label: str, net: np.ndarray, bk: np.ndarray) -> None:
    if len(net) < 3:
        print(f"  {label:>16} (too few: n={len(net)})")
        return
    t, p = ttest_1samp(net, 0)
    clo, chi = boot_ci(net, bk)
    py, ny = pos_years(net, bk)
    # Annualized metrics
    n_years = ny
    n_trades = len(net)
    trades_per_year = n_trades / n_years if n_years > 0 else 0
    ann_ret = net.mean() * trades_per_year / 100  # as fraction
    # Approx sharpe: assume vol per trade ≈ 50 bps, portfolio vol ≈ 50 * sqrt(n) / 100
    vol_pct = 0.10
    sharpe = ann_ret / vol_pct if vol_pct > 0 else 0
    print(f"  {label:>16} n={len(net):>4} net={net.mean():>+7.2f} t={t:>+5.2f} p={p:>6.3f} "
          f"hit={(net>0).mean()*100:>3.0f}% posYrs={py}/{ny} boot95=[{clo:>+6.2f},{chi:>+6.2f}] "
          f"tr/yr={trades_per_year:>4.1f} annRet={ann_ret*100:>+5.2f}% Sharpe≈{sharpe:>+4.2f}")


def continuation_study(sym: str, event_dates: list[date], hold_days: int = 1,
                         q_select: float = 1.0, warmup: int = 12) -> tuple[np.ndarray, np.ndarray]:
    """
    Chase the event move: if Friday up -> long Monday; if Friday down -> short Monday.
    Selectivity: only trade when |event move| is in top-q_select quantile of past events.
    """
    df = load_daily(sym)
    df = df.set_index("bucket").sort_index()
    mid = df["mid"].to_numpy()
    idx = df.index
    c = cost(sym)

    hist_abs_move: list[float] = []
    nets: list[float] = []
    bks: list[pd.Timestamp] = []

    for ed in event_dates:
        try:
            fri_loc = idx.get_loc(pd.Timestamp(ed))
        except KeyError:
            continue
        thu_loc = fri_loc - 1
        if thu_loc < 0:
            continue
        if not df.iloc[thu_loc]["contig"]:
            continue
        post_loc = fri_loc + hold_days
        if post_loc >= len(idx):
            continue
        if hold_days == 1 and not df.iloc[fri_loc]["contig"]:
            continue

        r_event = (np.log(mid[fri_loc]) - np.log(mid[thu_loc])) * 1e4
        r_post = (np.log(mid[post_loc]) - np.log(mid[fri_loc])) * 1e4
        abs_move = abs(r_event)

        if len(hist_abs_move) >= warmup:
            thr = np.quantile(hist_abs_move, q_select)
            if abs_move >= thr:
                # CHASE the move: same direction as event
                net = r_post - c if r_event > 0 else -r_post - c
                nets.append(net)
                bks.append(idx[fri_loc])
        hist_abs_move.append(abs_move)

    return np.array(nets), np.array(bks)


def main() -> None:
    events = nfp_dates(2018, 2025)
    print("=" * 110)
    print("MACRO EVENT CONTINUATION PROBE — US NFP (first-Friday), daily bars, real Razor cost")
    print(f"Events: {len(events)} NFP releases | hold = 1 or 2 trading days after Friday close")
    print("Strategy: CHASE the Friday move (long if Fri up, short if Fri down)")
    print("=" * 110)

    for hold in (1, 2):
        print(f"\n### Hold {hold} day(s) after Friday close ###")
        for q in (1.0, 0.90, 0.80, 0.70, 0.50, 0.30):
            print(f"\n  Selectivity: top-{int(q*100)}% of |event-day| moves (expanding window)")
            print(f"  {'pair':>8} {'netMean':>8} {'t':>6} {'p':>6} {'hit%':>4} {'posYrs':>7} {'boot95':>16} {'tr/yr':>5} {'annRet':>7} {'Sharpe':>6}")
            all_nets, all_bks = [], []
            for sym in PAIRS:
                net, bk = continuation_study(sym, events, hold_days=hold, q_select=q)
                if len(net) >= 3:
                    all_nets.append(net)
                    all_bks.append(bk)
                line(sym, net, bk)
            if all_nets:
                pooled_net = np.concatenate(all_nets)
                pooled_bk = np.concatenate(all_bks)
                line("POOLED", pooled_net, pooled_bk)

    # Per-pair breakdown: raw correlation
    print("\n" + "=" * 110)
    print("RAW CONTINUATION METRICS (no selectivity, all events)")
    print("=" * 110)
    for sym in PAIRS:
        df = load_daily(sym)
        df = df.set_index("bucket").sort_index()
        mid = df["mid"].to_numpy()
        idx = df.index
        c = cost(sym)
        nets, bks = [], []
        r_events, r_posts = [], []
        for ed in events:
            try:
                fri_loc = idx.get_loc(pd.Timestamp(ed))
            except KeyError:
                continue
            thu_loc = fri_loc - 1
            if thu_loc < 0 or not df.iloc[thu_loc]["contig"]:
                continue
            post_loc = fri_loc + 1
            if post_loc >= len(idx) or not df.iloc[fri_loc]["contig"]:
                continue
            r_event = (np.log(mid[fri_loc]) - np.log(mid[thu_loc])) * 1e4
            r_post = (np.log(mid[post_loc]) - np.log(mid[fri_loc])) * 1e4
            r_events.append(r_event)
            r_posts.append(r_post)
            net = r_post - c if r_event > 0 else -r_post - c
            nets.append(net)
            bks.append(idx[fri_loc])
        nets = np.array(nets)
        bks = np.array(bks)
        if len(r_events) >= 5:
            rho, pval = spearmanr(r_events, r_posts)
            print(f"\n{sym}: spearman(event, nextDay) = {rho:+.3f} (p={pval:.3f}, n={len(r_events)})")
        line(sym, nets, bks)

    # ROBUSTNESS: split-sample (2018-2021 vs 2022-2025)
    print("\n" + "=" * 110)
    print("SPLIT-SAMPLE ROBUSTNESS: 2018-2021 vs 2022-2025 (top-50% selectivity)")
    print("=" * 110)
    for sym in PAIRS:
        net_all, bk_all = continuation_study(sym, events, hold_days=1, q_select=0.50)
        if len(net_all) < 3:
            continue
        years = pd.to_datetime(bk_all).year
        mask_early = years <= 2021
        mask_late = years >= 2022
        if mask_early.sum() >= 3:
            line(f"{sym} 2018-21", net_all[mask_early], bk_all[mask_early])
        if mask_late.sum() >= 3:
            line(f"{sym} 2022-25", net_all[mask_late], bk_all[mask_late])

    # EVENT COUNT
    print("\n" + "=" * 110)
    print("TRADE FREQUENCY SUMMARY")
    print("=" * 110)
    for sym in PAIRS:
        for q in (1.0, 0.50):
            net, bk = continuation_study(sym, events, hold_days=1, q_select=q)
            if len(net) > 0:
                n_years = len(pd.to_datetime(bk).year.unique())
                print(f"{sym} top-{int(q*100)}%: {len(net)} trades over {n_years} years = {len(net)/n_years:.1f}/year")


if __name__ == "__main__":
    main()

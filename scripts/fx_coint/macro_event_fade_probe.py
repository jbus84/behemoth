"""Macro event fade probe: post-large-move mean-reversion on FX daily bars.

Tests whether large daily moves (top-pct by |return|) partially revert over
the next 1-2 trading days.  Focuses on mid-week events (Tue-Thu) where
macro announcements (FOMC, ECB, BOE) occur — no weekend gap contamination.
Uses causal expanding-window thresholds and real Razor cost.

Usage:
    uv run python scripts/fx_coint/macro_event_fade_probe.py
"""
from __future__ import annotations

import sys
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
    print(f"  {label:>16} n={len(net):>4} net={net.mean():>+7.2f} t={t:>+5.2f} p={p:>6.3f} "
          f"hit={(net>0).mean()*100:>3.0f}% posYrs={py}/{ny} boot95=[{clo:>+6.2f},{chi:>+6.2f}]")


def fade_study(sym: str, hold_days: int = 1, q_select: float = 0.90,
               weekday_filter: tuple[int, ...] = (0, 1, 2, 3, 4),
               warmup: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """
    Fade large daily moves: if day_t up -> short day_{t+1..t+H}; if down -> long.
    Selectivity: only trade when |day_t return| is in top-q_select quantile
    of past |daily returns| (expanding window, causal).
    weekday_filter: which weekdays to allow for entry (0=Mon, ..., 4=Fri).
    """
    df = load_daily(sym)
    df = df.set_index("bucket").sort_index()
    mid = df["mid"].to_numpy()
    idx = df.index
    c = cost(sym)

    r = df["ret_bps"].to_numpy()
    contig = df["contig"].to_numpy()
    dow = idx.dayofweek.to_numpy()

    hist_abs: list[float] = []
    nets: list[float] = []
    bks: list[pd.Timestamp] = []

    n = len(r)
    for i in range(n):
        if not contig[i] or np.isnan(r[i]) or dow[i] not in weekday_filter:
            continue
        if i + hold_days >= n:
            continue
        # Check post-hold contiguous
        if hold_days == 1 and not contig[i + 1]:
            continue

        abs_r = abs(r[i])
        if len(hist_abs) >= warmup:
            thr = np.quantile(hist_abs, q_select)
            if abs_r >= thr:
                fwd = (np.log(mid[i + hold_days]) - np.log(mid[i])) * 1e4
                # Fade: opposite direction of day_i move
                net = -fwd - c if r[i] > 0 else fwd - c
                nets.append(net)
                bks.append(idx[i])
        hist_abs.append(abs_r)

    return np.array(nets), np.array(bks)


def continuation_study(sym: str, hold_days: int = 1, q_select: float = 0.90,
                        weekday_filter: tuple[int, ...] = (0, 1, 2, 3, 4),
                        warmup: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """Chase (not fade) large daily moves."""
    df = load_daily(sym)
    df = df.set_index("bucket").sort_index()
    mid = df["mid"].to_numpy()
    idx = df.index
    c = cost(sym)

    r = df["ret_bps"].to_numpy()
    contig = df["contig"].to_numpy()
    dow = idx.dayofweek.to_numpy()

    hist_abs: list[float] = []
    nets: list[float] = []
    bks: list[pd.Timestamp] = []

    n = len(r)
    for i in range(n):
        if not contig[i] or np.isnan(r[i]) or dow[i] not in weekday_filter:
            continue
        if i + hold_days >= n:
            continue
        if hold_days == 1 and not contig[i + 1]:
            continue

        abs_r = abs(r[i])
        if len(hist_abs) >= warmup:
            thr = np.quantile(hist_abs, q_select)
            if abs_r >= thr:
                fwd = (np.log(mid[i + hold_days]) - np.log(mid[i])) * 1e4
                net = fwd - c if r[i] > 0 else -fwd - c  # chase
                nets.append(net)
                bks.append(idx[i])
        hist_abs.append(abs_r)

    return np.array(nets), np.array(bks)


def main() -> None:
    print("=" * 96)
    print("MACRO EVENT FADE PROBE — large daily move fade, causal thresholds, real Razor cost")
    print("Tests: top-pct |daily return| -> fade next 1-2 days")
    print("Mid-week = Tue-Thu (macro event days, no weekend gap)")
    print("=" * 96)

    # Compare: fade vs continuation, mid-week vs all-days
    for hold in (1, 2):
        for q in (0.90, 0.80, 0.70, 0.50):
            print(f"\n### Hold {hold}d | selectivity top-{int(q*100)}% |daily ret| ###")

            # FADE, mid-week only
            print(f"\n  FADE (mid-week entry Tue-Thu):")
            print(f"  {'pair':>8} {'netMean':>8} {'t':>6} {'p':>6} {'hit%':>4} {'posYrs':>7} {'boot95':>16}")
            all_nets_fade, all_bks_fade = [], []
            for sym in PAIRS:
                net, bk = fade_study(sym, hold_days=hold, q_select=q,
                                      weekday_filter=(1, 2, 3), warmup=60)
                if len(net) >= 3:
                    all_nets_fade.append(net)
                    all_bks_fade.append(bk)
                line(sym, net, bk)
            if all_nets_fade:
                line("POOLED", np.concatenate(all_nets_fade), np.concatenate(all_bks_fade))

            # FADE, all days (including Fri)
            print(f"\n  FADE (all days):")
            print(f"  {'pair':>8} {'netMean':>8} {'t':>6} {'p':>6} {'hit%':>4} {'posYrs':>7} {'boot95':>16}")
            all_nets_fade_all, all_bks_fade_all = [], []
            for sym in PAIRS:
                net, bk = fade_study(sym, hold_days=hold, q_select=q,
                                      weekday_filter=(0, 1, 2, 3, 4), warmup=60)
                if len(net) >= 3:
                    all_nets_fade_all.append(net)
                    all_bks_fade_all.append(bk)
                line(sym, net, bk)
            if all_nets_fade_all:
                line("POOLED", np.concatenate(all_nets_fade_all), np.concatenate(all_bks_fade_all))

            # CONTINUATION, mid-week only
            print(f"\n  CONTINUATION (mid-week entry Tue-Thu):")
            print(f"  {'pair':>8} {'netMean':>8} {'t':>6} {'p':>6} {'hit%':>4} {'posYrs':>7} {'boot95':>16}")
            all_nets_cont, all_bks_cont = [], []
            for sym in PAIRS:
                net, bk = continuation_study(sym, hold_days=hold, q_select=q,
                                            weekday_filter=(1, 2, 3), warmup=60)
                if len(net) >= 3:
                    all_nets_cont.append(net)
                    all_bks_cont.append(bk)
                line(sym, net, bk)
            if all_nets_cont:
                line("POOLED", np.concatenate(all_nets_cont), np.concatenate(all_bks_cont))

    # RAW CORRELATION: |day_t ret| vs day_{t+1} ret (mid-week only)
    print("\n" + "=" * 96)
    print("RAW CORRELATION: day_t return vs day_{t+1} return (mid-week only, all moves)")
    print("=" * 96)
    for sym in PAIRS:
        df = load_daily(sym)
        df = df.set_index("bucket").sort_index()
        r = df["ret_bps"].to_numpy()
        contig = df["contig"].to_numpy()
        dow = df.index.dayofweek.to_numpy()
        pairs = []
        for i in range(len(r) - 1):
            if contig[i] and contig[i+1] and dow[i] in (1, 2, 3) and np.isfinite(r[i]) and np.isfinite(r[i+1]):
                pairs.append((r[i], r[i+1]))
        if len(pairs) > 5:
            r0 = [x[0] for x in pairs]
            r1 = [x[1] for x in pairs]
            rho, pval = spearmanr(r0, r1)
            print(f"  {sym}: rho(day_t, day_t+1) = {rho:+.3f} (p={pval:.3f}, n={len(pairs)})")

    # SPLIT by magnitude: small vs large moves
    print("\n" + "=" * 96)
    print("MAGNITUDE DEPENDENCE: fade small vs large moves (mid-week, hold=1d)")
    print("=" * 96)
    for sym in PAIRS:
        df = load_daily(sym)
        df = df.set_index("bucket").sort_index()
        mid = df["mid"].to_numpy()
        r = df["ret_bps"].to_numpy()
        contig = df["contig"].to_numpy()
        idx = df.index
        dow = idx.dayofweek.to_numpy()
        c = cost(sym)

        hist_abs: list[float] = []
        small_nets, large_nets = [], []
        small_bks, large_bks = [], []
        for i in range(len(r)):
            if not contig[i] or np.isnan(r[i]) or dow[i] not in (1, 2, 3):
                continue
            if i + 1 >= len(r) or not contig[i+1]:
                continue
            abs_r = abs(r[i])
            fwd = (np.log(mid[i+1]) - np.log(mid[i])) * 1e4
            net = -fwd - c if r[i] > 0 else fwd - c
            if len(hist_abs) >= 60:
                p80 = np.quantile(hist_abs, 0.80)
                if abs_r >= p80:
                    large_nets.append(net)
                    large_bks.append(idx[i])
                else:
                    small_nets.append(net)
                    small_bks.append(idx[i])
            hist_abs.append(abs_r)

        if small_nets:
            line(f"{sym} small", np.array(small_nets), np.array(small_bks))
        if large_nets:
            line(f"{sym} LARGE", np.array(large_nets), np.array(large_bks))

    # Frequency summary
    print("\n" + "=" * 96)
    print("TRADE FREQUENCY (mid-week large moves, top-50% |ret|)")
    print("=" * 96)
    for sym in PAIRS:
        net, bk = fade_study(sym, hold_days=1, q_select=0.50,
                              weekday_filter=(1, 2, 3), warmup=60)
        if len(net) > 0:
            n_years = len(pd.to_datetime(bk).year.unique())
            print(f"{sym}: {len(net)} trades over {n_years} years = {len(net)/n_years:.1f}/year")


if __name__ == "__main__":
    main()

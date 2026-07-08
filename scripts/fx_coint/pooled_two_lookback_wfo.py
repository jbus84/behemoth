"""Pooled two-lookback WFO: honest test of short vs long memory regimes.

Instead of per-pair lookback selection (6 × 15 = 90 degrees of freedom),
select ONE lookback per year for the ENTIRE pooled book.

Candidate regimes: N ∈ {10, 100} only — short-memory vs long-memory.
Each year, pick the N that maximizes pooled Sharpe on prior data,
then trade ALL 6 pairs at that N for the next year.

This tests whether there are genuine regime shifts in reversion memory,
without per-pair overfitting.

Usage:
    uv run python scripts/fx_coint/pooled_two_lookback_wfo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402

rsh.FREQ_MINUTES["1d"] = 1440
RNG = np.random.default_rng(0)

COMM = 0.60
SPR = {"EURUSD": 0.1, "USDJPY": 0.1, "GBPUSD": 0.2, "USDCAD": 0.3, "AUDUSD": 0.15, "USDCHF": 0.3}
PX = {"EURUSD": 1.08, "USDJPY": 150.0, "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": 0.65, "USDCHF": 0.89}
ALL6 = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY"]
CANDIDATE_Ns = [10, 100]


def cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def daily_series(sym):
    bars = rsh.build_freq_bars(
        pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
        "1d",
        session=(0, 24),
    )
    mid = bars["mid"].to_numpy()
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~bars["contig"].to_numpy()] = np.nan
    return mid, r, bars["bucket"].to_numpy()


def causal_fade(sym, N, H, q=0.90, warmup=60, start_idx=None, end_idx=None):
    mid, r, bk = daily_series(sym)
    if start_idx is not None:
        mid = mid[start_idx:end_idx]
        r = r[start_idx:end_idx]
        bk = bk[start_idx:end_idx]
    rs = pd.Series(r)
    sig = (rs.rolling(N, min_periods=N // 2).sum() / (rs.rolling(20, min_periods=10).std() * np.sqrt(N))).to_numpy()
    n = len(mid)
    fwd = np.full(n, np.nan)
    fwd[: n - H] = (np.log(mid[H:]) - np.log(mid[: n - H])) * 1e4
    grid = np.arange(0, n, H)
    grid = grid[np.isfinite(sig[grid]) & np.isfinite(fwd[grid])]
    c = cost(sym)
    hist, nets, bks = [], [], []
    for gi in grid:
        s = sig[gi]
        if len(hist) >= warmup:
            hi = np.quantile(hist, q)
            lo = np.quantile(hist, 1 - q)
            if s >= hi:
                nets.append(-fwd[gi] - c)
                bks.append(bk[gi])
            elif s <= lo:
                nets.append(fwd[gi] - c)
                bks.append(bk[gi])
        hist.append(s)
    return np.array(nets), np.array(bks)


def pooled_book(pairs, N, H, start_idx=None, end_idx=None):
    """Pooled reversion book: equal-weight per trade, all pairs at same N."""
    nets, bks = [], []
    for sym in pairs:
        nn, bb = causal_fade(sym, N, H, start_idx=start_idx, end_idx=end_idx)
        if len(nn):
            nets.append(nn)
            bks.append(bb)
    return np.concatenate(nets), np.concatenate(bks)


def daily_pnl(net, bucket):
    s = pd.Series(net, index=pd.to_datetime(bucket).date)
    return s.groupby(level=0).mean()


def boot_ci(net, bucket, n_boot=3000):
    if len(net) < 3:
        return np.nan, np.nan
    s = pd.Series(net, index=pd.to_datetime(bucket).year)
    arrs = [g.to_numpy() for _, g in s.groupby(level=0)]
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = RNG.integers(0, len(arrs), len(arrs))
        means[b] = np.concatenate([arrs[i] for i in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def report(label, net, bk):
    if len(net) < 3:
        print(f"  {label:>18} (too few trades)")
        return None
    t, p = ttest_1samp(net, 0)
    clo, chi = boot_ci(net, bk)
    py, ny = pos_years(net, bk)
    d = daily_pnl(net, bk)
    sharpe = d.mean() / d.std() * np.sqrt(252) if d.std() > 0 else np.nan
    cum = d.cumsum()
    dd = (cum - cum.cummax()).min()
    print(
        f"  {label:>18} n={len(net):>5} net={net.mean():>+7.2f} t={t:>+6.2f} p={p:>6.3f} "
        f"hit={(net > 0).mean()*100:>4.0f}% posYrs={py}/{ny} Sharpe={sharpe:>+5.2f} maxDD={dd:>+8.2f} "
        f"boot95=[{clo:>+7.2f},{chi:>+7.2f}]"
    )
    return d


def pos_years(net, bucket):
    yr = pd.Series(net, index=pd.to_datetime(bucket).year).groupby(level=0).mean()
    return int((yr > 0).sum()), len(yr)


def wfo_two_lookback(H):
    """Walk-forward: each year pick N ∈ {10, 100} from prior pooled Sharpe."""
    # Need to align all series to same timeline
    # Build full book for each N, then split by year
    all_books = {}
    for N in CANDIDATE_Ns:
        nn, bb = pooled_book(ALL6, N, H)
        all_books[N] = (nn, bb)

    # Get year range
    years = sorted(set(pd.to_datetime(all_books[10][1]).year))
    if len(years) < 3:
        return np.array([]), np.array([]), []

    all_nets, all_bks, selections = [], [], []
    for i, trade_yr in enumerate(years[2:], start=2):
        train_years = years[:i]  # all prior years
        best_n = None
        best_sharpe = -np.inf
        for N in CANDIDATE_Ns:
            nn, bb = all_books[N]
            yr = pd.to_datetime(bb).year
            train_mask = np.isin(yr, train_years)
            train_nn = nn[train_mask]
            train_bb = bb[train_mask]
            if len(train_nn) < 10:
                continue
            d = daily_pnl(train_nn, train_bb)
            if d.std() > 0:
                sharpe = d.mean() / d.std() * np.sqrt(252)
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_n = N

        if best_n is None:
            continue

        # Trade the selected N on trade_yr
        nn, bb = all_books[best_n]
        yr = pd.to_datetime(bb).year
        trade_mask = yr == trade_yr
        trade_nn = nn[trade_mask]
        trade_bb = bb[trade_mask]
        if len(trade_nn):
            all_nets.append(trade_nn)
            all_bks.append(trade_bb)
            selections.append((trade_yr, best_n, best_sharpe))

    if not all_nets:
        return np.array([]), np.array([]), []
    return np.concatenate(all_nets), np.concatenate(all_bks), selections


def main():
    H = 3
    print("=" * 120)
    print("POOLED TWO-LOOKBACK WFO: N ∈ {10, 100} selected annually for entire book")
    print("=" * 120)

    # --- In-sample benchmarks ---
    print("\n--- In-sample benchmarks ---")
    for N in CANDIDATE_Ns:
        nn, bb = pooled_book(ALL6, N, H)
        report(f"pooled N={N}", nn, bb)

    # --- Two-lookback WFO ---
    print("\n--- Walk-forward: select N annually from prior pooled Sharpe ---")
    nn, bb, selections = wfo_two_lookback(H)
    if len(nn) > 0:
        report("WFO two-lookback", nn, bb)
        print("\n  Year-by-year selections:")
        for yr, n, sharpe in selections:
            print(f"    {yr}: selected N={n}  (train Sharpe={sharpe:+.2f})")
    else:
        print("  (no trades)")

    # --- Fixed N=10 WFO baseline ---
    print("\n--- Fixed N=10 WFO baseline (for comparison) ---")
    # For fixed N=10, just show in-sample since WFO doesn't change
    nn, bb = pooled_book(ALL6, 10, H)
    report("fixed N=10", nn, bb)

    print("\n" + "=" * 120)
    print("INTERPRETATION:")
    print("  - If WFO two-lookback Sharpe >> fixed N=10, regime-switching is real")
    print("  - If WFO ≈ fixed N=10, just use fixed N=10 (simpler, honest)")
    print("  - If WFO << fixed N=10, even 2-choice selection overfits")
    print("=" * 120)


if __name__ == "__main__":
    main()

"""WFO check on the validated daily reversion cell.

The original claim: fade past-10d extended move, hold 2-3 days non-overlap,
causal expanding-window deciles, pooled 6 pairs net +5.77 t2.47 p0.013.

But N=10 and H=2-3 were selected from an in-sample sweep. This script tests:
  1. Walk-forward: pick N annually from prior data (pooled Sharpe), trade next year
  2. Pick H annually from prior data
  3. Fixed N=10/H=2 with causal deciles (the original spec)

If even fixed-N WFO degrades, the lookback selection was overfit AND the
edge itself may not survive strict OOS.

Usage:
    uv run python scripts/fx_coint/daily_reversion_wfo.py
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
TIGHT3 = ["EURUSD", "GBPUSD", "USDJPY"]


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


def pos_years(net, bucket):
    yr = pd.Series(net, index=pd.to_datetime(bucket).year).groupby(level=0).mean()
    return int((yr > 0).sum()), len(yr)


def report(label, net, bk):
    if len(net) < 3:
        print(f"  {label:>22} (too few trades)")
        return None
    t, p = ttest_1samp(net, 0)
    clo, chi = boot_ci(net, bk)
    py, ny = pos_years(net, bk)
    d = daily_pnl(net, bk)
    sharpe = d.mean() / d.std() * np.sqrt(252) if d.std() > 0 else np.nan
    cum = d.cumsum()
    dd = (cum - cum.cummax()).min()
    print(
        f"  {label:>22} n={len(net):>5} net={net.mean():>+7.2f} t={t:>+6.2f} p={p:>6.3f} "
        f"hit={(net > 0).mean()*100:>4.0f}% posYrs={py}/{ny} Sharpe={sharpe:>+5.2f} maxDD={dd:>+8.2f} "
        f"boot95=[{clo:>+7.2f},{chi:>+7.2f}]"
    )
    return d


def wfo_select_nh(pairs, H, candidate_Ns, start_idx=None, end_idx=None):
    """For WFO: evaluate each N on training data, return pooled Sharpe."""
    results = {}
    for N in candidate_Ns:
        nn, bb = pooled_book(pairs, N, H, start_idx=start_idx, end_idx=end_idx)
        if len(nn) >= 10:
            d = daily_pnl(nn, bb)
            if d.std() > 0:
                results[N] = d.mean() / d.std() * np.sqrt(252)
    return results


def wfo_daily_reversion(pairs, candidate_Ns, candidate_Hs):
    """WFO: each year pick (N, H) from prior pooled Sharpe, trade next year."""
    # Build full books for all (N, H) combos
    all_books = {}
    for N in candidate_Ns:
        for H in candidate_Hs:
            nn, bb = pooled_book(pairs, N, H)
            all_books[(N, H)] = (nn, bb)

    # Determine year range from any one book
    sample_nn, sample_bb = all_books[(candidate_Ns[0], candidate_Hs[0])]
    years = sorted(set(pd.to_datetime(sample_bb).year))
    if len(years) < 3:
        return np.array([]), np.array([]), []

    all_nets, all_bks, selections = [], [], []
    for i, trade_yr in enumerate(years[2:], start=2):
        train_years = years[:i]
        best_nh = None
        best_sharpe = -np.inf
        for (N, H), (nn, bb) in all_books.items():
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
                    best_nh = (N, H)

        if best_nh is None:
            continue

        N, H = best_nh
        nn, bb = all_books[best_nh]
        yr = pd.to_datetime(bb).year
        trade_mask = yr == trade_yr
        trade_nn = nn[trade_mask]
        trade_bb = bb[trade_mask]
        if len(trade_nn):
            all_nets.append(trade_nn)
            all_bks.append(trade_bb)
            selections.append((trade_yr, N, H, best_sharpe))

    if not all_nets:
        return np.array([]), np.array([]), []
    return np.concatenate(all_nets), np.concatenate(all_bks), selections


def main():
    print("=" * 120)
    print("DAILY REVERSION WFO CHECK: is the validated cell overfit?")
    print("=" * 120)

    # --- In-sample benchmarks (the original claim) ---
    print("\n--- In-sample benchmarks (causal deciles, but N/H selected from full sample) ---")
    for pairs, label in [(TIGHT3, "tight3"), (ALL6, "all6")]:
        for H in (2, 3):
            nn, bb = pooled_book(pairs, 10, H)
            report(f"{label} N=10 H={H}", nn, bb)

    # --- WFO: pick N and H annually ---
    print("\n--- Walk-forward: select (N, H) annually from prior pooled Sharpe ---")
    candidate_Ns = [5, 10, 15, 20, 30]
    candidate_Hs = [2, 3]

    for pairs, label in [(TIGHT3, "tight3"), (ALL6, "all6")]:
        print(f"\n  {label.upper()}:")
        nn, bb, selections = wfo_daily_reversion(pairs, candidate_Ns, candidate_Hs)
        if len(nn) > 0:
            report(f"WFO {label}", nn, bb)
            print(f"  Selections: {[(s[0], f'N={s[1]} H={s[2]}') for s in selections]}")
        else:
            print("  (no trades)")

    # --- Also test fixed N=10/H=2 with causal deciles (no WFO, just honest fixed param) ---
    print("\n--- Honest fixed-parameter baseline (N=10, H=2, causal deciles, no param selection) ---")
    nn, bb = pooled_book(ALL6, 10, 2)
    report("fixed N=10 H=2 all6", nn, bb)
    nn, bb = pooled_book(TIGHT3, 10, 2)
    report("fixed N=10 H=2 tight3", nn, bb)

    print("\n" + "=" * 120)
    print("INTERPRETATION:")
    print("  - If WFO ≈ in-sample, the edge is real (parameter selection not overfit)")
    print("  - If WFO << in-sample, the validated cell is suspect")
    print("  - Tight3 (EUR/GBP/JPY) vs all6 matters — JPY may be the unstable component")
    print("=" * 120)


if __name__ == "__main__":
    main()

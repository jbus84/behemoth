"""Per-pair lookback combined book vs fixed-N pool.

Runs each major at its optimal deployable lookback (causal expanding-window deciles),
then combines daily PnL (equal weight per trade, or equal risk).

Optimal deployable params (boot95 clears 0 + Sharpe > 1.0):
  EURUSD  H=3 N=20
  GBPUSD  H=3 N=20
  AUDUSD  H=3 N=95
  USDCAD  H=2 N=30  (H=3 best N=80 but boot95 straddles)
  USDCHF  H=3 N=80
  USDJPY  H=3 N=100

Compares to fixed N=10/H=3 pool (all 6 pairs).

Usage:
    uv run python scripts/fx_coint/per_pair_lookback_book.py
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

# Per-pair optimal deployable params (sym -> (H, N))
OPTIMAL = {
    "EURUSD": (3, 20),
    "GBPUSD": (3, 20),
    "AUDUSD": (3, 95),
    "USDCAD": (2, 30),
    "USDCHF": (3, 80),
    "USDJPY": (3, 100),
}


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


def causal_fade(sym, N, H, q=0.90, warmup=60):
    mid, r, bk = daily_series(sym)
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


def main():
    print("=" * 120)
    print("PER-PAIR LOOKBACK BOOK vs FIXED N=10/H=3 POOL")
    print("=" * 120)

    # --- Fixed N=10/H=3 pool (all 6 pairs) ---
    print("\n--- Fixed pool: all 6 pairs @ N=10, H=3 ---")
    pool_nets, pool_bks = [], []
    for sym in ALL6:
        nn, bb = causal_fade(sym, 10, 3)
        if len(nn):
            pool_nets.append(nn)
            pool_bks.append(bb)
    pool_net = np.concatenate(pool_nets)
    pool_bk = np.concatenate(pool_bks)
    d_pool = report("fixed N=10 pool", pool_net, pool_bk)

    # --- Per-pair optimal book ---
    print("\n--- Per-pair optimal ---")
    daily_series_map = {}
    pair_stats = []
    for sym in ALL6:
        H, N = OPTIMAL[sym]
        nn, bb = causal_fade(sym, N, H)
        d = report(f"{sym}(H={H},N={N})", nn, bb)
        daily_series_map[sym] = d
        pair_stats.append({"sym": sym, "n": len(nn), "net": nn.mean() if len(nn) else np.nan})

    # --- Combined: equal-weight daily PnL ---
    print("\n--- Combined per-pair-optimal book ---")
    # Align all daily series
    all_idx = None
    for sym in ALL6:
        d = daily_series_map[sym]
        if d is not None:
            all_idx = d.index if all_idx is None else all_idx.union(d.index)

    if all_idx is not None and len(all_idx) > 10:
        # Equal weight (each pair gets 1/6 of book)
        combined_eq = pd.Series(0.0, index=all_idx)
        for sym in ALL6:
            d = daily_series_map[sym]
            if d is not None:
                combined_eq = combined_eq.add(d.reindex(all_idx, fill_value=0), fill_value=0)
        combined_eq /= 6  # equal weight

        net_arr = combined_eq.to_numpy()
        t, p = ttest_1samp(net_arr, 0)
        sharpe = net_arr.mean() / net_arr.std() * np.sqrt(252) if net_arr.std() > 0 else np.nan
        cum = combined_eq.cumsum()
        dd = (cum - cum.cummax()).min()
        # bootstrap on daily
        idx = pd.to_datetime(combined_eq.index)
        arrs = [g.to_numpy() for _, g in pd.Series(net_arr, index=idx.year).groupby(level=0)]
        means = np.empty(3000)
        for b in range(3000):
            pick = RNG.integers(0, len(arrs), len(arrs))
            means[b] = np.concatenate([arrs[i] for i in pick]).mean()
        clo, chi = float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
        yr = pd.Series(net_arr, index=idx.year).groupby(level=0).mean()
        py, ny = int((yr > 0).sum()), len(yr)
        print(
            f"  {'combined(eq)':>18} n={len(net_arr):>5} net={net_arr.mean():>+7.2f} t={t:>+6.2f} p={p:>6.3f} "
            f"hit={(net_arr > 0).mean()*100:>4.0f}% posYrs={py}/{ny} Sharpe={sharpe:>+5.2f} maxDD={dd:>+8.2f} "
            f"boot95=[{clo:>+7.2f},{chi:>+7.2f}]"
        )

        # Correlation matrix of pair daily PnLs
        print("\n--- Pair daily PnL correlation matrix ---")
        corr_df = pd.DataFrame(index=ALL6, columns=ALL6, dtype=float)
        for s1 in ALL6:
            for s2 in ALL6:
                d1 = daily_series_map[s1]
                d2 = daily_series_map[s2]
                if d1 is not None and d2 is not None:
                    common = d1.index.intersection(d2.index)
                    if len(common) >= 10:
                        corr_df.loc[s1, s2] = float(np.corrcoef(d1.loc[common].fillna(0), d2.loc[common].fillna(0))[0, 1])
        print(corr_df.round(3).to_string())

    print("\n" + "=" * 120)
    print("SUMMARY:")
    print("  - per-pair lookback = tuning the reversion family, not a new phenomenon")
    print("  - combined Sharpe vs fixed pool = the metric that matters")
    print("=" * 120)


if __name__ == "__main__":
    main()

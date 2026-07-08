"""USDJPY momentum probe: does JPY trend where majors revert?

USDJPY is structurally different (carry/risk-off/BoJ). The reversion edge FAILS on it
(net-negative, 3/7 years). If JPY trends rather than reverts, momentum (follow the
extension) should be net-positive — and low-correlated to the 5-major reversion book,
making it a genuine within-FX diversifier.

Tests:
  1. Causal momentum on USDJPY daily bars: follow top-q / bottom-q vol-normalized
     past-N-day move, hold H days, non-overlapping, expanding-window thresholds.
  2. Correlation of USDJPY momentum daily PnL vs pooled-5-major reversion PnL.

Usage:
    uv run python scripts/fx_coint/usdjpy_momentum_probe.py
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
MAJORS5 = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF"]


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


def causal_momentum(sym, N, H, q=0.90, warmup=60):
    """Follow past-N vol-normalized move, hold H days, NON-OVERLAPPING.
    Decile thresholds from EXPANDING window (causal)."""
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
                # strong up -> long (momentum)
                nets.append(fwd[gi] - c)
                bks.append(bk[gi])
            elif s <= lo:
                # strong down -> short (momentum)
                nets.append(-fwd[gi] - c)
                bks.append(bk[gi])
        hist.append(s)
    return np.array(nets), np.array(bks)


def causal_reversion(sym, N, H, q=0.90, warmup=60):
    """Fade past-N vol-normalized move (mirror of momentum). Same causal setup."""
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
                nets.append(-fwd[gi] - c)  # overbought -> short
                bks.append(bk[gi])
            elif s <= lo:
                nets.append(fwd[gi] - c)  # oversold -> long
                bks.append(bk[gi])
        hist.append(s)
    return np.array(nets), np.array(bks)


def pooled_reversion(N, H, q=0.90):
    """Pooled 5-major reversion book for orthogonality comparison."""
    nets, bks = [], []
    for sym in MAJORS5:
        nn, bb = causal_reversion(sym, N, H, q)
        if len(nn):
            nets.append(nn)
            bks.append(bb)
    return np.concatenate(nets), np.concatenate(bks)


def daily_pnl_series(net, bucket):
    """Aggregate per-trade net to daily mean PnL for correlation."""
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


def line(label, net, bk):
    if len(net) < 3:
        print(f"  {label:>16} (too few: n={len(net)})")
        return
    t, p = ttest_1samp(net, 0)
    clo, chi = boot_ci(net, bk)
    py, ny = pos_years(net, bk)
    print(
        f"  {label:>16} n={len(net):>4}  net={net.mean():>+6.2f}  "
        f"t={t:>+5.2f} p={p:>6.3f}  hit={(net > 0).mean() * 100:>4.0f}%  "
        f"posYrs={py}/{ny}  boot95=[{clo:>+6.2f},{chi:>+6.2f}]"
    )


def main():
    print("=" * 90)
    print("USDJPY MOMENTUM vs REVERSION — causal expanding-window deciles, non-overlapping")
    print("=" * 90)

    for N in (20, 50, 100, 200):
        print(f"\n--- Lookback N={N} days ---")
        for H in (2, 3, 5):
            print(f"\n  Hold H={H} days")
            # USDJPY momentum
            jpy_mom, jpy_mom_bk = causal_momentum("USDJPY", N, H)
            # USDJPY reversion (mirror)
            jpy_rev, jpy_rev_bk = causal_reversion("USDJPY", N, H)
            # Pooled 5-major reversion
            pool_rev, pool_rev_bk = pooled_reversion(N, H)

            line("USDJPY momentum", jpy_mom, jpy_mom_bk)
            line("USDJPY reversion", jpy_rev, jpy_rev_bk)
            line("5-maj reversion", pool_rev, pool_rev_bk)

            # Orthogonality: daily PnL correlation
            if len(jpy_mom) >= 3 and len(pool_rev) >= 3:
                d_jpy_mom = daily_pnl_series(jpy_mom, jpy_mom_bk)
                d_jpy_rev = daily_pnl_series(jpy_rev, jpy_rev_bk)
                d_pool = daily_pnl_series(pool_rev, pool_rev_bk)
                # Align on common dates
                common = d_jpy_mom.index.intersection(d_pool.index)
                if len(common) >= 10:
                    corr_mom = float(np.corrcoef(d_jpy_mom.loc[common].fillna(0), d_pool.loc[common].fillna(0))[0, 1])
                    print(f"  {'corr(JPYmom, poolRev)':>16}  {corr_mom:>+6.3f}  (n_days={len(common)})")
                common_rev = d_jpy_rev.index.intersection(d_pool.index)
                if len(common_rev) >= 10:
                    corr_rev = float(np.corrcoef(d_jpy_rev.loc[common_rev].fillna(0), d_pool.loc[common_rev].fillna(0))[0, 1])
                    print(f"  {'corr(JPYrev, poolRev)':>16}  {corr_rev:>+6.3f}  (n_days={len(common_rev)})")

    print("\n" + "=" * 90)
    print("Interpretation:")
    print("  - USDJPY momentum positive + low corr to 5-major reversion = orthogonal diversifier")
    print("  - USDJPY reversion negative (as prior) = confirms JPY is momentum-dominated")
    print("  - Correlation near zero = independent PnL streams")
    print("=" * 90)


if __name__ == "__main__":
    main()

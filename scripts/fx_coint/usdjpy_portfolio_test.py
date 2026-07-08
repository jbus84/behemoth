"""Portfolio improvement test: does adding USDJPY (N=100) to the validated 5-major
reversion book (N=10) improve risk-adjusted returns?

Tests:
  1. 5-major reversion book standalone  (N=10, H=2/3, validated params)
  2. USDJPY reversion standalone        (N=100, H=2/3)
  3. Combined book                       (equal trade-weight within leg, or risk-parity)

Metrics: net, t, boot95, hit%, posYrs, daily Sharpe, max DD, corr, combined Sharpe vs standalone.

Usage:
    uv run python scripts/fx_coint/usdjpy_portfolio_test.py
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


def causal_fade(sym, N, H, q=0.90, warmup=60):
    """Fade past-N vol-normalized move, hold H days, NON-OVERLAPPING, expanding-window deciles."""
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


def daily_pnl_series(net, bucket):
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


def book_metrics(label, net, bk):
    if len(net) < 3:
        return
    t, p = ttest_1samp(net, 0)
    clo, chi = boot_ci(net, bk)
    py, ny = pos_years(net, bk)
    # daily series
    d = daily_pnl_series(net, bk)
    sharpe = d.mean() / d.std() * np.sqrt(252) if d.std() > 0 else np.nan
    # max drawdown from daily cumulative
    cum = d.cumsum()
    dd = (cum - cum.cummax()).min()
    print(
        f"  {label:>16} n={len(net):>5}  net={net.mean():>+7.3f}  "
        f"t={t:>+6.2f} p={p:>6.3f}  hit={(net > 0).mean() * 100:>4.0f}%  "
        f"posYrs={py}/{ny}  Sharpe={sharpe:>+5.2f}  maxDD={dd:>+7.2f}  "
        f"boot95=[{clo:>+7.2f},{chi:>+7.2f}]"
    )
    return d


def main():
    print("=" * 110)
    print("PORTFOLIO TEST: 5-major reversion (N=10) + USDJPY reversion (N=100), H=2/3")
    print("=" * 110)

    for H in (2, 3):
        print(f"\n--- Hold H={H} days ---")

        # 5-major reversion book at N=10 (validated params)
        pool_net, pool_bk = [], []
        for sym in MAJORS5:
            nn, bb = causal_fade(sym, 10, H)
            if len(nn):
                pool_net.append(nn)
                pool_bk.append(bb)
        pool_net = np.concatenate(pool_net)
        pool_bk = np.concatenate(pool_bk)
        d_pool = book_metrics("5maj(N=10)", pool_net, pool_bk)

        # USDJPY at N=100
        jpy_net, jpy_bk = causal_fade("USDJPY", 100, H)
        d_jpy = book_metrics("JPY(N=100)", jpy_net, jpy_bk)

        # Combined: equal trade-weight (simplest) — average the daily PnL
        if d_pool is not None and d_jpy is not None:
            common = d_pool.index.intersection(d_jpy.index)
            if len(common) >= 10:
                c_pool = d_pool.loc[common].fillna(0)
                c_jpy = d_jpy.loc[common].fillna(0)
                # equal weight
                d_comb_eq = (c_pool + c_jpy) / 2
                # risk-parity weight (inverse vol)
                vol_pool = c_pool.std() or 1.0
                vol_jpy = c_jpy.std() or 1.0
                w_pool = (1 / vol_pool) / (1 / vol_pool + 1 / vol_jpy)
                w_jpy = (1 / vol_jpy) / (1 / vol_pool + 1 / vol_jpy)
                d_comb_rp = w_pool * c_pool + w_jpy * c_jpy

                # Print combined stats
                for lbl, d_series, w_p, w_j in [
                    ("combined(eq)", d_comb_eq, 0.5, 0.5),
                    ("combined(RP)", d_comb_rp, w_pool, w_jpy),
                ]:
                    net_arr = d_series.to_numpy()
                    t, p = ttest_1samp(net_arr, 0)
                    sharpe = net_arr.mean() / net_arr.std() * np.sqrt(252) if net_arr.std() > 0 else np.nan
                    cum = d_series.cumsum()
                    dd = (cum - cum.cummax()).min()
                    idx = pd.to_datetime(d_series.index)
                    # bootstrap on daily
                    arrs = [g.to_numpy() for _, g in pd.Series(net_arr, index=idx.year).groupby(level=0)]
                    means = np.empty(3000)
                    for b in range(3000):
                        pick = RNG.integers(0, len(arrs), len(arrs))
                        means[b] = np.concatenate([arrs[i] for i in pick]).mean()
                    clo, chi = float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
                    yr = pd.Series(net_arr, index=idx.year).groupby(level=0).mean()
                    py, ny = int((yr > 0).sum()), len(yr)
                    print(
                        f"  {lbl:>16} n={len(net_arr):>5}  net={net_arr.mean():>+7.3f}  "
                        f"t={t:>+6.2f} p={p:>6.3f}  hit={(net_arr > 0).mean() * 100:>4.0f}%  "
                        f"posYrs={py}/{ny}  Sharpe={sharpe:>+5.2f}  maxDD={dd:>+7.2f}  "
                        f"boot95=[{clo:>+7.2f},{chi:>+7.2f}]  w=(maj={w_p:.2f},jpy={w_j:.2f})"
                    )

                # Correlation
                corr = float(np.corrcoef(c_pool, c_jpy)[0, 1])
                print(f"  {'corr(pool,JPY)':>16}  {corr:>+7.3f}  (n_days={len(common)})")

    print("\n" + "=" * 110)
    print("Interpretation: combined Sharpe > max(standalone) = diversification benefit")
    print("=" * 110)


if __name__ == "__main__":
    main()

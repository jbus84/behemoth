"""USDJPY reversion sweep: N=30..100 trade-frequency vs net frontier.

Tests USDJPY reversion (causal expanding-window deciles) at lookbacks N=30..100
in steps of 5, hold H=2/3, with full stats + correlation to 5-major pool(N=10).

Usage:
    uv run python scripts/fx_coint/usdjpy_n_sweep.py
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


def pooled_fade(pairs, N, H, q=0.90):
    nets, bks = [], []
    for sym in pairs:
        nn, bb = causal_fade(sym, N, H, q)
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


def run(H):
    print(f"\n{'='*110}")
    print(f"H={H} days  —  USDJPY reversion sweep N=30..100, step=5")
    print(f"{'='*110}")
    print(f"{'N':>3} {'n':>5} {'net':>7} {'t':>6} {'p':>6} {'hit':>5} "
          f"{'posYrs':>6} {'Sharpe':>6} {'maxDD':>8} {'boot95':>24} {'corrPool':>8}")

    # Pre-build pool daily series for correlation
    pool_net, pool_bk = pooled_fade(MAJORS5, 10, H)
    d_pool = daily_pnl(pool_net, pool_bk)

    rows = []
    for N in range(30, 105, 5):
        nn, bb = causal_fade("USDJPY", N, H)
        if len(nn) < 3:
            continue
        t, p = ttest_1samp(nn, 0)
        clo, chi = boot_ci(nn, bb)
        py, ny = pos_years(nn, bb)
        d_jpy = daily_pnl(nn, bb)
        sharpe = d_jpy.mean() / d_jpy.std() * np.sqrt(252) if d_jpy.std() > 0 else np.nan
        cum = d_jpy.cumsum()
        dd = (cum - cum.cummax()).min()
        # correlation to pool
        common = d_jpy.index.intersection(d_pool.index)
        if len(common) >= 10:
            corr = float(np.corrcoef(d_jpy.loc[common].fillna(0), d_pool.loc[common].fillna(0))[0, 1])
        else:
            corr = np.nan
        print(
            f"{N:>3} {len(nn):>5} {nn.mean():>+7.2f} {t:>+6.2f} {p:>6.3f} "
            f"{(nn > 0).mean()*100:>4.0f}% {py}/{ny} {sharpe:>+6.2f} {dd:>+8.2f} "
            f"[{clo:>+7.2f},{chi:>+7.2f}] {corr:>+8.3f}"
        )
        rows.append({"N": N, "n": len(nn), "net": nn.mean(), "t": t, "p": p,
                     "sharpe": sharpe, "dd": dd, "corr": corr, "boot_lo": clo, "boot_hi": chi})

    # Summary
    if rows:
        best_net = max(rows, key=lambda r: r["net"])
        best_sharpe = max(rows, key=lambda r: r["sharpe"] if not np.isnan(r["sharpe"]) else -np.inf)
        best_n = max(rows, key=lambda r: r["n"])
        print(f"\n  Best net:    N={best_net['N']:.0f}  net={best_net['net']:.2f}  n={best_net['n']}")
        print(f"  Best Sharpe: N={best_sharpe['N']:.0f}  Sharpe={best_sharpe['sharpe']:.2f}  n={best_sharpe['n']}")
        print(f"  Most trades: N={best_n['N']:.0f}  n={best_n['n']}")


def main():
    print("USDJPY REVERSION SWEEP: trade-frequency vs net frontier")
    run(2)
    run(3)
    print("\n" + "=" * 110)
    print("INTERPRETATION:")
    print("  - Higher n = more overlap with pool = richer combined book")
    print("  - Sharpe > 1.0 + boot95 clears 0 = deployable threshold")
    print("  - corrPool < 0.3 = low correlation, diversifier potential")
    print("=" * 110)


if __name__ == "__main__":
    main()

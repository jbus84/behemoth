"""Validate the H=2-3 day reversion cell across ALL 21 pairs (6 majors + 15 crosses).

Extends validate_reversion_cell.py with cross-pair cost estimates.
Same causal methodology: expanding-window OOS decile thresholds, non-overlapping holds.
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
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
ALL6 = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "USDCHF"]
CROSSES = [
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURCHF",
    "AUDCAD", "GBPAUD", "EURAUD", "GBPCHF", "CADJPY",
    "CHFJPY", "NZDUSD", "EURNZD", "GBPNZD", "AUDNZD",
]
ALL21 = ALL6 + CROSSES
RNG = np.random.default_rng(0)

COMM = 0.60

# Spreads in pips (major = from original; crosses = estimates based on typical Razor)
SPR = {
    # Majors
    "EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3,
    # Crosses (estimates)
    "EURGBP": .2, "EURJPY": .2, "GBPJPY": .3, "AUDJPY": .3, "EURCHF": .2,
    "AUDCAD": .3, "GBPAUD": .4, "EURAUD": .3, "GBPCHF": .3, "CADJPY": .3,
    "CHFJPY": .3, "NZDUSD": .2, "EURNZD": .4, "GBPNZD": .5, "AUDNZD": .4,
}

# Approximate prices for cost calc
PX = {
    "EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89,
    "EURGBP": 0.85, "EURJPY": 165., "GBPJPY": 192., "AUDJPY": 98., "EURCHF": 0.94,
    "AUDCAD": 0.91, "GBPAUD": 1.92, "EURAUD": 1.65, "GBPCHF": 1.13, "CADJPY": 109.,
    "CHFJPY": 170., "NZDUSD": 0.59, "EURNZD": 1.75, "GBPNZD": 2.10, "AUDNZD": 1.08,
}


def cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def daily_series(sym):
    bars = rsh.build_freq_bars(pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
                               "1d", session=(0, 24))
    mid = bars["mid"].to_numpy()
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~bars["contig"].to_numpy()] = np.nan
    return mid, r, bars["bucket"].to_numpy()


def causal_fade(sym, L, H, q=0.90, warmup=60):
    """Fade past-L vol-normalized move, hold H days, NON-OVERLAPPING, causal decile thresholds."""
    mid, r, bk = daily_series(sym)
    rs = pd.Series(r)
    sig = (rs.rolling(L, min_periods=L // 2).sum()
           / (rs.rolling(20, min_periods=10).std() * np.sqrt(L))).to_numpy()
    n = len(mid)
    fwd = np.full(n, np.nan)
    fwd[:n - H] = (np.log(mid[H:]) - np.log(mid[:n - H])) * 1e4
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


def pooled(pairs, L, H):
    nets, bks = [], []
    for sym in pairs:
        nn, bb = causal_fade(sym, L, H)
        if len(nn):
            nets.append(nn)
            bks.append(bb)
    return np.concatenate(nets), np.concatenate(bks)


def line(label, net, bk):
    if len(net) < 3:
        print(f"  {label:>16} (too few: n={len(net)})")
        return
    t, p = ttest_1samp(net, 0)
    clo, chi = boot_ci(net, bk)
    py, ny = pos_years(net, bk)
    print(f"  {label:>16} n={len(net):>4} net={net.mean():>+7.2f} t={t:>+5.2f} p={p:>6.3f} "
          f"hit={(net > 0).mean()*100:>3.0f}% pos={py}/{ny} boot95=[{clo:>+6.2f},{chi:>+6.2f}]")


def main():
    print("=" * 86)
    print("CAUSAL re-test (expanding-window OOS decile thresholds) of the H=2-3 reversion cell")
    print("FULL 21-PAIR: 6 majors + 15 crosses, net estimated Razor cost")
    print("=" * 86)
    print("\nR1 — lookback (L) x horizon (H) robustness (ALL 21 POOLED):")
    for H in (2, 3):
        for L in (5, 10, 15, 20, 30, 60):
            net, bk = pooled(ALL21, L, H)
            line(f"H={H} L={L}", net, bk)
        print()

    print("=" * 86)
    print("R2 — all 21 pairs at headline cell (L=10, H=2)")
    print("=" * 86)
    npos = 0
    for sym in ALL21:
        net, bk = causal_fade(sym, 10, 2)
        if len(net) >= 3:
            npos += net.mean() > 0
        line(sym, net, bk)
    net, bk = pooled(ALL21, 10, 2)
    line("POOLED 21", net, bk)
    net, bk = pooled(ALL6, 10, 2)
    line("POOLED 6 (majors)", net, bk)
    net, bk = pooled(CROSSES, 10, 2)
    line("POOLED 15 (crosses)", net, bk)
    net, bk = pooled([s for s in ALL6 if s != "USDJPY"], 10, 2)
    line("MAJORS ex-JPY", net, bk)
    print(f"\n  -> {npos}/21 pairs net-positive at L=10,H=2 (causal).")


if __name__ == "__main__":
    main()

"""Cross-sectional dollar-neutral MOMENTUM — second market-neutral leg.

Same residual space as xs_reversion (USD factor removed by cross-sectional demean) but
the opposite behaviour: RIDE the longer residual trend instead of fading the short one.
  w_c = +zscore(rolling-L residual)   (long leaders, short laggards), dollar-neutral.
If reversion dominates at short L and momentum at long L (the usual FX shape), these two
market-neutral legs occupy different lookbacks and should diversify each other AND the
directional TB book.

Sweeps L and reports Sharpe / maxDD / per-year, plus correlation to the XS reversion
(L=20) and — the point — whether a long-L momentum leg is independently positive.

Usage: uv run python scripts/fx_coint/xs_momentum.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.xs_reversion as xsr

L_GRID = [10, 20, 40, 60, 120]
XS_REV_L = 20


def backtest_mom(resid, L):
    """Ride rolling-L residual trend, dollar-neutral daily-rebalanced. Returns daily net bps."""
    sig = resid.rolling(L, min_periods=max(2, L // 2)).sum()
    z = sig.sub(sig.mean(axis=1), axis=0).div(sig.std(axis=1) + 1e-9, axis=0)
    w = z                                            # momentum: long leaders
    w = w.sub(w.mean(axis=1), axis=0)
    gross = w.abs().sum(axis=1).replace(0, np.nan)
    w = w.div(gross, axis=0).shift(1)
    avg_cost = np.mean(list(xsr.COST_BPS.values()))
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    return ((w * resid).sum(axis=1) - turn * avg_cost * xsr.TURN_COST_FRAC).dropna()


def stats(pnl):
    if len(pnl) < 50:
        return None
    sharpe = pnl.mean() / (pnl.std() + 1e-9) * np.sqrt(252)
    cum = pnl.cumsum()
    dd = (cum - cum.cummax()).min()
    yr = pnl.groupby(pnl.index.year).sum()
    return dict(n=len(pnl), mean=pnl.mean(), sharpe=sharpe, total=cum.iloc[-1], maxdd=dd,
                pos=int((yr > 0).sum()), ny=len(yr), yr=yr)


def main():
    xsr.TURN_COST_FRAC = 1.0
    resid = xsr.residualise(xsr.daily_returns())
    rev = xsr.backtest(resid, XS_REV_L)
    rev.index = pd.to_datetime(rev.index)

    print("Cross-sectional dollar-neutral MOMENTUM (full cost)")
    print(f"{'L':>4s} {'dailyMean':>10s} {'Sharpe':>7s} {'totalBps':>9s} {'maxDD':>8s} "
          f"{'posYrs':>7s} {'corr(XSrev)':>11s}")
    best = None
    for L in L_GRID:
        p = backtest_mom(resid, L)
        s = stats(p)
        if s is None:
            continue
        p.index = pd.to_datetime(p.index)
        corr = pd.concat([p.rename("m"), rev.rename("r")], axis=1).dropna().corr().iloc[0, 1]
        print(f"{L:>4d} {s['mean']:>+10.3f} {s['sharpe']:>7.2f} {s['total']:>+9.0f} "
              f"{s['maxdd']:>+8.0f} {s['pos']:>4d}/{s['ny']} {corr:>+11.2f}")
        if best is None or s["sharpe"] > best[1]["sharpe"]:
            best = (L, s)
    if best:
        L, s = best
        print(f"\nBest momentum L={L}: per-year net bps")
        print("  " + "  ".join(f"{y}:{v:+.0f}" for y, v in s["yr"].items()))


if __name__ == "__main__":
    main()

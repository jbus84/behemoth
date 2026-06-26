"""Optimize the TB(N) x XS-reversion blend for max Calmar (not 50/50).

Reuses the canonical TB book (1000-tick ffd_zvol20 triple-barrier fade) at several N and
the market-neutral XS reversion (L=20, full cost). Both put on unit daily vol so the
blend weight w = XS share is a fair risk weight. For each (N, w) reports combined
Sharpe / maxDD / Calmar / positive-years. Picks max-Calmar, and prints the Calmar curve
across w so we can see whether the optimum is a robust PLATEAU or a fragile spike
(forking-path check: in-sample weight selection is only trustworthy if the surface is flat).

Usage: uv run python scripts/fx_coint/xs_tb_blend_opt.py
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

import scripts.fx_coint.xs_plus_tbreal_portfolio as mod

N_GRID = [20, 30, 40, 50]
W_GRID = [round(w, 2) for w in np.arange(0.0, 1.01, 0.1)]    # XS weight


def _unit(s):
    return s / (s.std() + 1e-9)


def metrics(s):
    sh = s.mean() / (s.std() + 1e-9) * np.sqrt(252)
    cum = s.cumsum()
    dd = (cum - cum.cummax()).min()
    cal = (s.mean() * 252) / (abs(dd) + 1e-9)
    yr = s.groupby(s.index.year).sum()
    return sh, dd, cal, int((yr > 0).sum()), len(yr)


def main():
    xs = mod.xs_daily()
    xs.index = pd.to_datetime(xs.index)
    xs_u = _unit(xs)

    print(f"{'N':>4s} {'wXS*':>5s} {'Sharpe':>7s} {'maxDD':>8s} {'Calmar':>7s} {'posYr':>6s}   Calmar curve over wXS=0..1")
    best = None
    for n in N_GRID:
        mod.N_TB = n
        tb = mod.daily_from_trades(mod.tb_trades())
        tb.index = pd.to_datetime(tb.index)
        df = pd.concat([_unit(tb).rename("tb"), xs_u.rename("xs")], axis=1).dropna(how="all").fillna(0.0)

        curve = []
        rowbest = None
        for w in W_GRID:
            comb = (1 - w) * df["tb"] + w * df["xs"]
            sh, dd, cal, pos, ny = metrics(comb)
            curve.append(cal)
            if rowbest is None or cal > rowbest[1]:
                rowbest = (w, cal, sh, dd, pos, ny)
            if best is None or cal > best[2]:
                best = (n, w, cal, sh, dd, pos, ny)
        w, cal, sh, dd, pos, ny = rowbest
        spark = " ".join(f"{c:+.2f}" for c in curve)
        print(f"{n:>4d} {w:>5.1f} {sh:>7.2f} {dd:>8.1f} {cal:>7.2f} {pos:>3d}/{ny}   {spark}")

    n, w, cal, sh, dd, pos, ny = best
    print(f"\nBEST: N={n}, wXS={w:.1f}  -> Calmar={cal:.2f} Sharpe={sh:.2f} maxDD={dd:.1f} pos={pos}/{ny}")
    print("(curve columns are wXS = 0.0, 0.1, ... 1.0; look for a flat plateau, not a spike)")


if __name__ == "__main__":
    main()

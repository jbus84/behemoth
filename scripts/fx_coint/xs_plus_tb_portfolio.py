"""Does cross-sectional reversion COMPLEMENT the existing TB reversion book?

Combines two daily PnL streams:
  A. TB reversion (weekly_trades from st55_weekly_portfolio): the existing directional
     fade-extended-move book (long when extended down, short when extended up).
  B. XS reversion (xs_reversion): market-neutral dollar-neutral residual fade, L=20,
     charged at FULL turnover cost (honest).

Both are put on the SAME daily bps scale (each normalised to unit daily vol so the
combination is a fair 50/50 risk blend, not dominated by whichever is louder). Reports
correlation, each-alone vs combined Sharpe / max-DD / Calmar, per-year, and the return
when the combined book is sized to a 10% max-drawdown budget.

Usage: uv run python scripts/fx_coint/xs_plus_tb_portfolio.py
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
from scripts.fx_coint.st55_weekly_portfolio import daily_pnl, weekly_trades

PAIRS = list(xsr.PAIRS)
XS_L = 20


def tb_daily():
    """Existing TB reversion book: pooled weekly fade trades -> daily bps series."""
    frames = []
    for sym in PAIRS:
        t = weekly_trades(sym)
        if len(t):
            frames.append(t)
    allt = pd.concat(frames, ignore_index=True)
    return daily_pnl(allt)


def xs_daily():
    xsr.TURN_COST_FRAC = 1.0          # honest full cost
    resid = xsr.residualise(xsr.daily_returns())
    p = xsr.backtest(resid, XS_L)
    p.index = pd.to_datetime(p.index)
    return p


def _unit_vol(s):
    return s / (s.std() + 1e-9)


def report(name, s):
    sharpe = s.mean() / (s.std() + 1e-9) * np.sqrt(252)
    cum = s.cumsum()
    dd = (cum - cum.cummax()).min()
    calmar = (s.mean() * 252) / (abs(dd) + 1e-9)
    yr = s.groupby(s.index.year).sum()
    print(f"{name:14s} Sharpe={sharpe:5.2f}  maxDD={dd:8.2f}  Calmar={calmar:5.2f}  "
          f"posYears={int((yr > 0).sum())}/{len(yr)}")
    return yr


def main():
    tb = tb_daily()
    xs = xs_daily()
    tb.index = pd.to_datetime(tb.index)
    df = pd.concat([tb.rename("TB"), xs.rename("XS")], axis=1).dropna(how="all").fillna(0.0)
    corr = df["TB"].corr(df["XS"])
    print(f"Daily-PnL correlation TB vs XS: {corr:+.3f}\n")

    # unit-vol blend so neither dominates
    tb_u, xs_u = _unit_vol(df["TB"]), _unit_vol(df["XS"])
    combined = 0.5 * tb_u + 0.5 * xs_u

    yr_tb = report("TB (unit-vol)", tb_u)
    yr_xs = report("XS (unit-vol)", xs_u)
    yr_co = report("COMBINED", combined)

    print("\nPer-year (unit-vol bps):")
    print(f"  {'year':>5s} {'TB':>8s} {'XS':>8s} {'COMB':>8s}")
    for y in sorted(set(yr_tb.index) | set(yr_xs.index)):
        print(f"  {y:>5d} {yr_tb.get(y, 0):>+8.1f} {yr_xs.get(y, 0):>+8.1f} {yr_co.get(y, 0):>+8.1f}")

    # size combined to 10% max-DD budget
    cum = combined.cumsum()
    dd = abs((cum - cum.cummax()).min())
    scale = 0.10 / (dd / 1e4) if dd > 0 else np.nan        # dd in bps -> fraction
    ann = combined.mean() * 252 / 1e4 * scale
    print(f"\nSized to 10% max-DD: scale={scale:.2f}x  -> est annual return ~{ann * 100:.1f}% "
          f"(combined Calmar {(combined.mean() * 252) / (dd + 1e-9):.2f})")


if __name__ == "__main__":
    main()

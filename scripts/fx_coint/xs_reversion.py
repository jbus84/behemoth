"""Cross-sectional dollar-neutral reversion — orthogonal to the USD-directional family.

Every edge built so far (st55 directional, 2-3d fade, weekly MR) is the SAME USD-factor
reversion/momentum bet, so 2022/2024/2026 chop sinks them together. The structural fix
is to remove the common USD factor and trade only the currency-SPECIFIC residual:

  1. Convert each major to a currency-vs-USD return (orient USDxxx pairs).
  2. Demean across the 6 currencies each day  -> residual = USD factor removed.
  3. Signal_c = rolling-L sum of residual (the extended currency-specific move).
  4. FADE it cross-sectionally: weight w_c = -zscore(signal_c), dollar-neutral
     (sum w ~ 0), gross-normalised. Daily PnL = sum_c w_c * residual_ret_next, minus
     turnover cost. This is what a market-neutral long-laggard / short-leader book earns.

Because the book is dollar-neutral, it is structurally orthogonal to any directional
USD move. We sweep the reversion lookback L and report annualised Sharpe, max drawdown,
per-year net, and (the point) correlation to the directional weekly MR.

Usage: uv run python scripts/fx_coint/xs_reversion.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
# currency-vs-USD orientation: +1 means pair return already = currency-up-vs-USD
PAIRS = {"EURUSD": +1, "GBPUSD": +1, "AUDUSD": +1, "USDCAD": -1, "USDCHF": -1, "USDJPY": -1}
COST_BPS = rsh.COST_BPS
L_GRID = [3, 5, 10, 20, 40]
TURN_COST_FRAC = 0.5     # fraction of round-trip cost charged per unit weight change


def daily_returns():
    """Aligned daily currency-vs-USD log returns (bps) for the 6 majors."""
    series = {}
    for sym, sign in PAIRS.items():
        df1m = pl.read_parquet(f"{DATA}/{sym}_1m_flow.parquet")
        bars = rsh.build_freq_bars(df1m, "1d", session=(0, 24))
        mid = bars["mid"].to_numpy()
        bk = pd.to_datetime(bars["bucket"].to_numpy())
        r = np.empty(len(mid))
        r[0] = np.nan
        r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4 * sign
        series[sym] = pd.Series(r, index=bk)
    R = pd.DataFrame(series).sort_index()
    return R


def residualise(R):
    """Cross-sectional demean each day -> currency-specific residual returns (USD factor out)."""
    return R.sub(R.mean(axis=1), axis=0)


def backtest(resid, L):
    """Fade rolling-L residual move, dollar-neutral daily-rebalanced book. Returns daily net bps."""
    sig = resid.rolling(L, min_periods=max(2, L // 2)).sum()
    z = sig.sub(sig.mean(axis=1), axis=0).div(sig.std(axis=1) + 1e-9, axis=0)
    w = -z                                          # fade: short leaders, long laggards
    w = w.sub(w.mean(axis=1), axis=0)               # enforce dollar-neutral
    gross = w.abs().sum(axis=1).replace(0, np.nan)
    w = w.div(gross, axis=0)                         # gross exposure = 1
    w = w.shift(1)                                   # causal: trade on yesterday's signal

    # average per-pair round-trip cost in bps, charged on weight turnover
    avg_cost = np.mean(list(COST_BPS.values()))
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    pnl = (w * resid).sum(axis=1) - turn * avg_cost * TURN_COST_FRAC
    return pnl.dropna()


def stats(pnl):
    if len(pnl) < 50:
        return None
    mean, sd = pnl.mean(), pnl.std()
    sharpe = mean / (sd + 1e-9) * np.sqrt(252)
    cum = pnl.cumsum()
    dd = (cum - cum.cummax()).min()
    yr = pnl.groupby(pnl.index.year).sum()
    return dict(n=len(pnl), mean=mean, sharpe=sharpe, total=cum.iloc[-1], maxdd=dd,
                pos_years=int((yr > 0).sum()), n_years=len(yr), yr=yr)


def main():
    R = daily_returns()
    resid = residualise(R)
    print(f"Cross-sectional dollar-neutral reversion | {len(R)} days {R.index[0].date()}..{R.index[-1].date()}")
    print(f"{'L':>4s} {'days':>6s} {'dailyMean':>10s} {'Sharpe':>7s} {'totalBps':>9s} "
          f"{'maxDD':>9s} {'posYears':>9s}")
    best = None
    for L in L_GRID:
        s = stats(backtest(resid, L))
        if s is None:
            continue
        print(f"{L:>4d} {s['n']:>6d} {s['mean']:>+10.3f} {s['sharpe']:>7.2f} {s['total']:>+9.0f} "
              f"{s['maxdd']:>+9.0f} {s['pos_years']:>4d}/{s['n_years']}")
        if best is None or s["sharpe"] > best[1]["sharpe"]:
            best = (L, s)
    if best:
        L, s = best
        print(f"\nBest L={L}: per-year net bps")
        print("  " + "  ".join(f"{y}:{v:+.0f}" for y, v in s["yr"].items()))


if __name__ == "__main__":
    main()

"""Metaorders worked over multiple bars: is there a tradeable flow-continuation?

Premise (correct): big orders are split and executed over many bars, so order FLOW is
injected over time -> persistent same-direction pressure. Test on hourly bars (flow_tick,
flow_ofi), pooled 6 majors, USD-oriented:

  1. FLOW ACF      : autocorrelation of flow at lags 1..20. High/slow-decaying = orders
                     ARE worked over bars (confirms the premise).
  2. RETURN ACF    : for contrast — is price still efficient (~0)?
  3. FLOW-MOMENTUM : does sign(rolling-k flow) predict the next-h return? (the during-
                     execution continuation). Unconditional IC.
  4. CONDITIONAL   : restrict to bars where recent flow is most PERSISTENT (sustained
                     same-sign run / high |rolling flow|) — a metaorder is most likely
                     active — and re-measure flow->return. If continuation is tradeable
                     anywhere, it is here.

Usage: uv run python scripts/fx_coint/flow_persistence_probe.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.feature_ic_definitive import DATA

PAIRS = {"EURUSD": +1, "GBPUSD": +1, "AUDUSD": +1, "USDCAD": -1, "USDCHF": -1, "USDJPY": -1}
H = 3            # forward horizon (bars) for return
K = 3            # rolling window for sustained flow


def load(sym, sgn):
    import polars as pl
    d = pl.read_parquet(f"{DATA}/{sym}_1h_flow.parquet").sort("bucket").to_pandas()
    logp = np.log(d["mid"].to_numpy())
    n = len(logp)
    r = np.append(np.nan, np.diff(logp)) * 1e4 * sgn          # oriented 1-bar return
    ft = d["flow_tick"].to_numpy() * sgn                       # oriented flow
    fo = d["flow_ofi"].to_numpy() * sgn
    fwd = np.full(n, np.nan)
    fwd[:n - H] = (logp[H:] - logp[:n - H]) * 1e4 * sgn
    return r, ft, fo, fwd


def acf(x, lag):
    x = x[np.isfinite(x)]
    x = x - x.mean()
    return np.sum(x[lag:] * x[:-lag]) / np.sum(x * x)


def main():
    R, FT, FO, FWD = [], [], [], []
    for s, sgn in PAIRS.items():
        r, ft, fo, fwd = load(s, sgn)
        R.append(r)
        FT.append(ft)
        FO.append(fo)
        FWD.append(fwd)

    print("1. FLOW ACF (flow_tick) vs RETURN ACF — is flow worked over bars while price stays efficient?")
    print(f"   {'lag':>4s} {'flow_acf':>9s} {'ret_acf':>9s}")
    for lag in [1, 2, 3, 5, 10, 20]:
        fa = np.mean([acf(ft, lag) for ft in FT])
        ra = np.mean([acf(r, lag) for r in R])
        print(f"   {lag:>4d} {fa:>+9.4f} {ra:>+9.4f}")

    # pool for IC tests
    ft = np.concatenate(FT)
    fo = np.concatenate(FO)
    fwd = np.concatenate(FWD)
    # rolling-K sustained flow per symbol
    roll = np.concatenate([pd.Series(x).rolling(K).sum().to_numpy() for x in FT])
    runlen = np.concatenate([
        (pd.Series(np.sign(x)).groupby((np.sign(x) != np.sign(pd.Series(x).shift())).cumsum()).cumcount() + 1).to_numpy()
        for x in FT])

    def ic(x, y):
        m = np.isfinite(x) & np.isfinite(y)
        return spearmanr(x[m], y[m]).correlation if m.sum() > 500 else np.nan

    print("\n3. FLOW-MOMENTUM -> fwd return (unconditional Spearman IC)")
    print(f"   flow_tick      : {ic(ft, fwd):+.4f}")
    print(f"   flow_ofi       : {ic(fo, fwd):+.4f}")
    print(f"   rollK flow_tick: {ic(roll, fwd):+.4f}")

    print("\n4. CONDITIONAL on metaorder likely active (sustained flow):")
    for q in [0.0, 0.9, 0.99]:
        if q == 0:
            m = np.isfinite(roll)
            lbl = "all"
        else:
            thr = np.nanquantile(np.abs(roll), q)
            m = np.isfinite(roll) & (np.abs(roll) >= thr)
            lbl = f"|rollFlow|>=q{q}"
        # follow the sustained flow: sign(roll)*fwd
        val = (np.sign(roll[m]) * fwd[m])
        val = val[np.isfinite(val)]
        print(f"   {lbl:>16s}  n={len(val):>7d}  mean(sign(rollFlow)*fwd)={val.mean():+.3f} bps  "
              f"IC={ic(roll[m], fwd[m]):+.4f}")
    # also condition on long same-sign flow runs
    print("\n   by flow run-length (consecutive same-sign flow bars):")
    for rl in [1, 2, 3, 5]:
        m = np.isfinite(roll) & np.isfinite(fwd) & (runlen >= rl)
        val = np.sign(roll[m]) * fwd[m]
        print(f"   run>={rl}: n={m.sum():>7d}  mean(sign(rollFlow)*fwd)={val[np.isfinite(val)].mean():+.3f} bps")


if __name__ == "__main__":
    main()

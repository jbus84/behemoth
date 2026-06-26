"""Order-flow imbalance as a directional signal on hourly bars (orthogonal sniff).

flow_tick (tick-rule signed flow) and flow_ofi (Cont OFI) are on the hourly bars. Test
whether they predict the NEXT-H-bar return — pooled 6 majors, per-symbol z-scored,
causal first-half/second-half split — in three forms:
  raw flow         : does own-bar flow predict own next return? (continuation/impact)
  flow change      : does the change in flow predict?
  residual flow    : flow with the cross-sectional (USD-factor) flow removed -> the
                     currency-specific flow, vs the residual return (market-neutral).
Reports IS/OOS IC and a quick net (trade sign(flow), top-decile |flow|, cost). A
positive, OOS-stable, cost-clearing result that is low-corr to reversion = a new edge.

Usage: uv run python scripts/fx_coint/flow_imbalance_probe.py
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
H = 3
COST = 1.0


def load(sym):
    import polars as pl
    df = pl.read_parquet(f"{DATA}/{sym}_1h_flow.parquet").sort("bucket")
    return df.to_pandas()


def build():
    frames = {}
    for sym, sgn in PAIRS.items():
        d = load(sym)
        logp = np.log(d["mid"].to_numpy())
        n = len(logp)
        fwd = np.full(n, np.nan)
        fwd[:n - H] = (logp[H:] - logp[:n - H]) * 1e4 * sgn        # USD-oriented fwd
        ft = d["flow_tick"].to_numpy() * sgn                        # USD-oriented flow
        fo = d["flow_ofi"].to_numpy() * sgn
        t = pd.DatetimeIndex(pd.to_datetime(d["bucket"].to_numpy()))
        frames[sym] = pd.DataFrame({"t": t, "fwd": fwd, "ft": ft, "fo": fo,
                                    "ftd": np.append(np.nan, np.diff(ft))}, index=t)
    # cross-sectional residual flow (remove USD-factor flow = mean across pairs at each time)
    ft_wide = pd.concat({s: frames[s]["ft"] for s in PAIRS}, axis=1)
    resid_ft = ft_wide.sub(ft_wide.mean(axis=1), axis=0)
    fwd_wide = pd.concat({s: frames[s]["fwd"] for s in PAIRS}, axis=1)
    resid_fwd = fwd_wide.sub(fwd_wide.mean(axis=1), axis=0)
    return frames, resid_ft, resid_fwd


def ic_split(x, y):
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(df) < 200:
        return np.nan, np.nan
    cut = len(df) // 2
    i_is = spearmanr(df["x"][:cut], df["y"][:cut]).correlation
    i_oos = spearmanr(df["x"][cut:], df["y"][cut:]).correlation
    return i_is, i_oos


def main():
    frames, resid_ft, resid_fwd = build()
    # pool raw
    ft = np.concatenate([frames[s]["ft"].to_numpy() for s in PAIRS])
    fo = np.concatenate([frames[s]["fo"].to_numpy() for s in PAIRS])
    ftd = np.concatenate([frames[s]["ftd"].to_numpy() for s in PAIRS])
    fwd = np.concatenate([frames[s]["fwd"].to_numpy() for s in PAIRS])
    rft = resid_ft.to_numpy().T.ravel()
    rfwd = resid_fwd.to_numpy().T.ravel()

    print(f"Flow imbalance -> fwd-{H}h return, pooled 6 majors, USD-oriented. IS | OOS Spearman IC")
    for name, x, y in (("flow_tick -> fwd", ft, fwd),
                       ("flow_ofi  -> fwd", fo, fwd),
                       ("d(flow_tick) -> fwd", ftd, fwd),
                       ("RESID flow_tick -> RESID fwd", rft, rfwd)):
        i_is, i_oos = ic_split(x, y)
        flag = "OOS-stable" if np.isfinite(i_is) and np.isfinite(i_oos) and np.sign(i_is) == np.sign(i_oos) and abs(i_oos) > 0.02 else ""
        print(f"  {name:32s} {i_is:>+7.4f} | {i_oos:>+7.4f}  {flag}")


if __name__ == "__main__":
    main()

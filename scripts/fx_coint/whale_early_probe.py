"""Can we catch the whale EARLY? Fresh-flow-surge continuation (front-loaded impact).

Square-root impact law: a metaorder's price impact is front-loaded, so any followable
continuation should be strongest at the START of the metaorder, not after a long run
(which we already found ~+0.04 bps, sub-cost). Test early detection on hourly bars:

  FRESH SURGE = flow_tick now in the top decile AND the prior W-bar flow was small
                (whale just started, not mid-run). Follow sign(flow) for N bars.
  by RUN POSITION = mean(sign(flow)*fwd) at run position 1 (just started) vs 2,3,4+
                    -> is continuation front-loaded (pos1 strongest)?
  ACCEL surge = large positive change in |flow| (flow accelerating in).

Pooled 6 majors, USD-oriented, causal first-half/second-half split, real cost on a
follow trade. If early whale-following clears cost it shows here; else it is closed.

Usage: uv run python scripts/fx_coint/whale_early_probe.py
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

from scripts.fx_coint.feature_ic_definitive import DATA

PAIRS = {"EURUSD": +1, "GBPUSD": +1, "AUDUSD": +1, "USDCAD": -1, "USDCHF": -1, "USDJPY": -1}
N_GRID = [1, 2, 3, 5]
PRIOR_W = 3
COST = 1.0


def load(sym, sgn):
    import polars as pl
    d = pl.read_parquet(f"{DATA}/{sym}_1h_flow.parquet").sort("bucket").to_pandas()
    logp = np.log(d["mid"].to_numpy())
    n = len(logp)
    ft = d["flow_tick"].to_numpy() * sgn
    fwd = {N: np.full(n, np.nan) for N in N_GRID}
    for N in N_GRID:
        fwd[N][:n - N] = (logp[N:] - logp[:n - N]) * 1e4 * sgn
    s = pd.Series(np.abs(ft))
    prior = s.shift(1).rolling(PRIOR_W).mean().to_numpy()      # recent flow magnitude
    sgn_ft = np.sign(ft)
    runpos = (pd.Series(sgn_ft).groupby((pd.Series(sgn_ft) != pd.Series(sgn_ft).shift()).cumsum()).cumcount() + 1).to_numpy()
    dflow = np.append(np.nan, np.diff(np.abs(ft)))             # flow acceleration (in)
    return dict(ft=ft, fwd=fwd, prior=prior, runpos=runpos, dflow=dflow, absft=np.abs(ft))


def main():
    D = {s: load(s, sgn) for s, sgn in PAIRS.items()}
    ft = np.concatenate([D[s]["ft"] for s in PAIRS])
    prior = np.concatenate([D[s]["prior"] for s in PAIRS])
    absft = np.concatenate([D[s]["absft"] for s in PAIRS])
    runpos = np.concatenate([D[s]["runpos"] for s in PAIRS])
    dflow = np.concatenate([D[s]["dflow"] for s in PAIRS])
    fwd = {N: np.concatenate([D[s]["fwd"][N] for s in PAIRS]) for N in N_GRID}

    hi = np.nanquantile(absft, 0.90)
    lo = np.nanquantile(prior[np.isfinite(prior)], 0.50)
    fresh = (absft >= hi) & (prior <= lo)        # big flow now, quiet before = fresh surge

    print("FRESH SURGE (big flow now, quiet prior) — mean(sign(flow)*fwd_N) bps, follow")
    print(f"   n_fresh={int(np.sum(fresh & np.isfinite(prior)))}")
    for N in N_GRID:
        m = fresh & np.isfinite(fwd[N]) & (ft != 0)
        v = np.sign(ft[m]) * fwd[N][m]
        print(f"   N={N}: {v.mean():+.3f}  (net~{v.mean() - COST:+.2f})")

    print("\nBY RUN POSITION (is continuation front-loaded?) mean(sign(flow)*fwd_1)")
    for rp in [1, 2, 3, 5, 8]:
        m = (runpos == rp) & np.isfinite(fwd[1]) & (ft != 0)
        if m.sum() > 200:
            v = np.sign(ft[m]) * fwd[1][m]
            print(f"   runpos={rp}: n={m.sum():>7d}  {v.mean():+.3f} bps")

    print("\nFLOW ACCELERATION (top-decile d|flow|) follow mean(sign(flow)*fwd_N)")
    da = np.nanquantile(dflow[np.isfinite(dflow)], 0.90)
    acc = dflow >= da
    for N in N_GRID:
        m = acc & np.isfinite(fwd[N]) & (ft != 0)
        v = np.sign(ft[m]) * fwd[N][m]
        print(f"   N={N}: n={m.sum():>7d}  {v.mean():+.3f}  (net~{v.mean() - COST:+.2f})")


if __name__ == "__main__":
    main()

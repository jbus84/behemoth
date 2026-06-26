"""Trending vs oscillatory vs random-walk: variance ratio + autocorrelation structure.

Plots show moves persisting over many bars (look trending/oscillatory), yet sign(vel)*fwd
is slightly negative. Reconcile with the proper diagnostics on 1000-tick mid log-returns,
pooled 5 majors:

  VARIANCE RATIO  VR(k) = Var(k-bar ret) / (k * Var(1-bar ret))
     VR>1 = trending/persistent, VR<1 = mean-reverting/oscillatory, VR=1 = random walk.
     Mapped across k to find the timescale of any structure.

  RETURN ACF      autocorrelation of 1-bar returns at lags 1..20
     persistent +ACF = momentum; alternating/neg = reversion; ~0 = random walk.

  LEVEL ACF       autocorrelation of the ffd_0.1 deviation (the thing we fade)
     slow decay = a persistent oscillation around fair value (= the reversion edge).

  RUN LENGTHS     mean consecutive same-sign-return run vs random-walk expectation (~2)
     >2 = persistence (what the eye reads as 'trends').

Usage: uv run python scripts/fx_coint/structure_analysis.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.feature_ic_definitive import build_all

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
VR_K = [2, 3, 5, 10, 20, 50, 100]
ACF_LAGS = [1, 2, 3, 5, 10, 20]


def variance_ratio(r, k):
    r = r[np.isfinite(r)]
    n = len(r)
    var1 = np.var(r)
    # k-bar non-overlapping sums
    m = (n // k) * k
    rk = r[:m].reshape(-1, k).sum(axis=1)
    vark = np.var(rk)
    return vark / (k * var1 + 1e-18)


def acf(x, lag):
    x = x[np.isfinite(x)]
    x = x - x.mean()
    return np.sum(x[lag:] * x[:-lag]) / np.sum(x * x)


def run_lengths(r):
    s = np.sign(r[np.isfinite(r) & (r != 0)])
    if len(s) < 2:
        return np.nan
    change = np.concatenate([[True], s[1:] != s[:-1]])
    starts = np.where(change)[0]
    lengths = np.diff(np.concatenate([starts, [len(s)]]))
    return lengths.mean()


def main():
    rets, ffds = [], []
    for s in POOL:
        logp, f, vol, bph = build_all(s)
        r = np.diff(logp)
        rets.append(r)
        ffds.append(f["ffd_0.1"])
    # pool VR / ACF by averaging per-symbol estimates
    print("VARIANCE RATIO VR(k)  (>1 trending, <1 mean-reverting, =1 random walk)")
    for k in VR_K:
        vr = np.mean([variance_ratio(r, k) for r in rets])
        tag = "trend" if vr > 1.05 else ("revert" if vr < 0.95 else "~RW")
        print(f"   k={k:>4}  VR={vr:.3f}  {tag}")

    print("\nRETURN ACF (1-bar returns)  (+ = momentum, - = reversion)")
    for lag in ACF_LAGS:
        a = np.mean([acf(r, lag) for r in rets])
        print(f"   lag={lag:>3}  acf={a:+.4f}")

    print("\nLEVEL ACF (ffd_0.1 deviation we fade)  (slow decay = persistent oscillation)")
    for lag in [1, 5, 20, 50, 100, 200]:
        a = np.mean([acf(f, lag) for f in ffds])
        print(f"   lag={lag:>4}  acf={a:+.4f}")

    rl = np.mean([run_lengths(r) for r in rets])
    print(f"\nMean same-sign run length: {rl:.2f}  (random-walk expectation ~2.0; >2 = persistence)")


if __name__ == "__main__":
    main()

"""Do bursts cluster, and when does the next one come? (timing vs direction)

A big move arrives as one burst. Test whether bursts self-excite (Hawkes / vol
clustering) and — crucially — whether the clustering is tradeable (direction) or only
timing/magnitude. 1000-tick bars, top-1% |return| = a 'burst', pooled 6 majors.

  1. TIMING      : inter-burst gap (bars) distribution; P(another burst within k bars
                   right after a burst) vs the 1% baseline. Clustered => >> baseline.
  2. MAGNITUDE   : mean |return| in the K bars after a burst vs unconditional (vol echo).
  3. DIRECTION   : corr(sign(burst_i), sign(burst_{i+1})); and after a +burst, the mean
                   SIGNED return over next K bars (continuation>0 / reversion<0). This is
                   the only tradeable part — is the next burst's direction predictable?

Usage: uv run python scripts/fx_coint/burst_clustering_probe.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.feature_ic_definitive import DATA

PAIRS = {"EURUSD": +1, "GBPUSD": +1, "AUDUSD": +1, "USDCAD": -1, "USDCHF": -1, "USDJPY": -1}
SUFFIX = "1000tick"
K_AFTER = [1, 2, 5, 10, 20]


def main():
    gaps = []
    next_within = {k: [] for k in K_AFTER}
    abs_after = {k: [] for k in K_AFTER}
    signed_after = {k: [] for k in K_AFTER}
    dir_pairs = []           # (sign burst_i, sign burst_{i+1})
    base_absr = []

    for sym, sgn in PAIRS.items():
        d = pl.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet").sort("timestamp")
        mid = (d["close_bid"].to_numpy() + d["close_ask"].to_numpy()) / 2
        logp = np.log(mid)
        n = len(logp)
        r = np.append(np.nan, np.diff(logp)) * 1e4 * sgn       # oriented bar return
        ar = np.abs(r)
        base_absr.append(ar[np.isfinite(ar)])
        thr = np.nanquantile(ar[np.isfinite(ar)], 0.99)
        burst = np.where(ar >= thr)[0]
        burst = burst[(burst > 20) & (burst < n - max(K_AFTER) - 1)]

        gaps.append(np.diff(burst))
        bset = set(burst.tolist())
        for bi in burst:
            for k in K_AFTER:
                # another burst in (bi, bi+k]?
                next_within[k].append(int(any((bi + j) in bset for j in range(1, k + 1))))
                seg = r[bi + 1: bi + 1 + k]
                abs_after[k].append(np.nanmean(np.abs(seg)))
                signed_after[k].append(np.sign(r[bi]) * np.nansum(seg))   # +=continuation
        # direction of consecutive bursts
        for a, b in zip(burst[:-1], burst[1:]):
            dir_pairs.append((np.sign(r[a]), np.sign(r[b])))

    g = np.concatenate(gaps)
    base = np.concatenate(base_absr)
    base_abs_mean = base.mean()
    print(f"BURST CLUSTERING ({SUFFIX}, top-1% |ret| bursts, pooled 6 majors)")
    print(f"  inter-burst gap (bars): median={np.median(g):.0f}  mean={np.mean(g):.0f}  "
          f"(random-Poisson mean ~100); p10={np.quantile(g, .1):.0f} p50={np.quantile(g, .5):.0f}")

    print("\n  1. TIMING — P(another burst within k bars | just had one) vs 1% baseline:")
    for k in K_AFTER:
        p = np.mean(next_within[k])
        base_p = 1 - (0.99 ** k)
        print(f"     k={k:>3}: {p:.3f}  vs baseline {base_p:.3f}  ({p / base_p:.1f}x)")

    print("\n  2. MAGNITUDE — mean |ret| in k bars after a burst vs unconditional:")
    for k in K_AFTER:
        m = np.nanmean(abs_after[k])
        print(f"     k={k:>3}: {m:.2f} bps  vs uncond {base_abs_mean:.2f}  ({m / base_abs_mean:.1f}x)")

    print("\n  3. DIRECTION (the tradeable part):")
    dp = np.array(dir_pairs)
    same = np.mean(dp[:, 0] == dp[:, 1])
    print(f"     consecutive-burst same-direction rate: {same:.3f} (0.5=random, >0.5 continue, <0.5 reverse)")
    for k in K_AFTER:
        s = np.nanmean(signed_after[k])
        print(f"     mean signed move {k} bars after burst (cont>0/rev<0): {s:+.2f} bps")


if __name__ == "__main__":
    main()

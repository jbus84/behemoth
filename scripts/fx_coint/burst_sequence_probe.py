"""Lie in wait for the next SAME-DIRECTION burst — is a tight cluster a continuing whale?

Aggregate consecutive-burst same-direction rate was 0.508 (~random), but that averages
over all gaps. Test conditional on the gap: a burst firing 1-2 bars after the last is
plausibly the SAME metaorder still working (same direction, rideable); a far one is
unrelated. 1000-tick, top-1% |ret| bursts, pooled 6 majors.

  1. SAME-DIRECTION rate of (burst_i, burst_{i+1}) split by gap bucket.
  2. If we enter at burst_i in its direction and hold to the next burst, the realised
     move (continuation>0) by gap bucket — could we ride the cluster?
  3. Tradeable: enter at a burst, hold K bars, net of cost, conditional on tight cluster.

Usage: uv run python scripts/fx_coint/burst_sequence_probe.py
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
GAP_BUCKETS = [(1, 1), (2, 3), (4, 10), (11, 30), (31, 100000)]
COST = 1.0


def main():
    recs = []          # (gap, sign_i, sign_next, move_i_to_next_in_dir_of_i)
    for sym, sgn in PAIRS.items():
        d = pl.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet").sort("timestamp")
        logp = np.log((d["close_bid"].to_numpy() + d["close_ask"].to_numpy()) / 2)
        n = len(logp)
        r = np.append(np.nan, np.diff(logp)) * 1e4 * sgn
        ar = np.abs(r)
        thr = np.nanquantile(ar[np.isfinite(ar)], 0.99)
        burst = np.where(ar >= thr)[0]
        burst = burst[(burst > 20) & (burst < n - 1)]
        for a, b in zip(burst[:-1], burst[1:]):
            gap = b - a
            move = (logp[b] - logp[a]) * 1e4 * sgn * np.sign(r[a])   # move from i to next, in dir of burst_i
            recs.append((gap, np.sign(r[a]), np.sign(r[b]), move))
    R = np.array(recs)
    gap, si, sn, mv = R[:, 0], R[:, 1], R[:, 2], R[:, 3]

    print(f"BURST SEQUENCE ({SUFFIX}, top-1% bursts) — same-direction & ride-to-next-burst by gap")
    print(f"  {'gap(bars)':>10s} {'n':>7s} {'sameDir':>8s} {'move i->next (dir of i)':>24s}")
    for lo, hi in GAP_BUCKETS:
        m = (gap >= lo) & (gap <= hi)
        if m.sum() < 50:
            continue
        same = np.mean(si[m] == sn[m])
        gap_lbl = f"{lo}-{hi}" if hi < 1000 else f"{lo}+"
        print(f"  {gap_lbl:>10s} {m.sum():>7d} {same:>8.3f} {np.mean(mv[m]):>+18.2f} bps")

    # tradeable: enter in burst direction, hold K bars, net of cost (does riding pay?)
    print("\n  RIDE the burst: enter in burst_i direction, hold K bars, net of cost")
    # rebuild per-symbol forward returns for clean hold
    for K in [1, 2, 5, 10]:
        pnls = []
        for sym, sgn in PAIRS.items():
            d = pl.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet").sort("timestamp")
            logp = np.log((d["close_bid"].to_numpy() + d["close_ask"].to_numpy()) / 2)
            nn = len(logp)
            r = np.append(np.nan, np.diff(logp)) * 1e4 * sgn
            ar = np.abs(r)
            thr = np.nanquantile(ar[np.isfinite(ar)], 0.99)
            bu = np.where(ar >= thr)[0]
            bu = bu[(bu > 20) & (bu < nn - K - 1)]
            fwd = (logp[bu + K] - logp[bu]) * 1e4 * sgn
            pnls.append(np.sign(r[bu]) * fwd - COST)          # ride continuation
        p = np.concatenate(pnls)
        print(f"     K={K:>3}: net={p.mean():+.2f} bps  hit={np.mean(p + COST > 0):.3f}  n={len(p)}")


if __name__ == "__main__":
    main()

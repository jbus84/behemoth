"""Are there SELECTABLE needles? Tail-reversion fade, net of REAL entry spread.

The average minute reversion is sub-cost, but a strategy only trades the subset it
can flag ex-ante. Test: stratify trigger bars by move size |r_t| (and entry-spread
state), fade the move at t+1 crossing actual bid/ask, hold k min, exit crossing
actual bid/ask. Net per stratum, hit-rate, N, pooled + cross-pair sign agreement.

Fade = bet on reversion: r_t>0 -> SELL at bid_{t+1}, buy back at ask_{t+1+k}.
Net captures the realised reversion MINUS the real round-trip spread at that moment
(wide spreads on spikes are included — that is the point).

A needle = a stratum with mean net > 0, sign-stable across pairs, with real N.

Usage:  uv run python scripts/fx_coint/minute_reversion_tail.py
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

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
HOLDS = [1, 3, 5, 10, 15]
ABS_BINS = [(2, 5), (5, 10), (10, 20), (20, 50), (50, 1e9)]  # |r_t| bps buckets


def load(sym):
    d = pl.read_parquet(f"data/tick_bars/{sym}_1m_flow.parquet").sort("bucket")
    mid = d["mid"].to_numpy().astype(np.float64)
    bid = d["bid"].to_numpy().astype(np.float64)
    ask = d["ask"].to_numpy().astype(np.float64)
    t = d["bucket"].to_numpy().astype("datetime64[m]").astype(np.int64)
    r = np.empty(len(mid)); r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    contig = np.empty(len(mid), dtype=bool); contig[0] = False
    contig[1:] = (t[1:] - t[:-1]) == 1
    r[~contig] = np.nan
    return mid, bid, ask, r, t


def fade_net_bps(bid, ask, mid, t, trig, k, follow=False):
    """For trigger rows `trig`, trade at t+1, hold k, exit. follow=False fades the
    move (bet reversion); follow=True goes with it (bet continuation). Returns net
    bps aligned to all rows; requires contiguous minutes t..t+1+k."""
    n = len(mid)
    net = np.full(n, np.nan)
    idx = np.where(trig)[0]
    idx = idx[idx + 1 + k < n]
    e = idx + 1            # entry bar
    x = idx + 1 + k        # exit bar
    # require contiguity entry..exit (no weekend gap inside the trade)
    ok = (t[x] - t[idx]) == (1 + k)
    idx, e, x = idx[ok], e[ok], x[ok]
    move = np.sign(mid[idx] - mid[idx - 1])  # = sign(r_t), the move just completed
    sgn = move if follow else -move          # follow=with the move; else fade
    short = sgn < 0
    long = sgn > 0
    prof = np.full(len(idx), np.nan)
    m = mid[idx]
    # short: sell bid_e, buy ask_x  -> bid_e - ask_x
    prof[short] = (bid[e][short] - ask[x][short]) / m[short] * 1e4
    # long: buy ask_e, sell bid_x   -> bid_x - ask_e
    prof[long] = (bid[x][long] - ask[e][long]) / m[long] * 1e4
    net[idx] = prof
    return net


def main():
    print("=== TAIL-REVERSION FADE  (net of REAL entry/exit spread, 6 pairs) ===")
    data = {p: load(p) for p in PAIRS}
    cost_ref = {}
    for p in PAIRS:
        mid, bid, ask, r, t = data[p]
        spr = (ask - bid) / mid * 1e4
        cost_ref[p] = np.nanmedian(spr)
    print("median spread (bps, ~round-trip cost): " +
          "  ".join(f"{p[:6]}={cost_ref[p]:.2f}" for p in PAIRS))

    for follow, name in [(False, "FADE (bet reversion)"), (True, "MOMENTUM (bet continuation)")]:
        print(f"\n################ {name} ################")
        for k in HOLDS:
            print(f"\n--- HOLD k={k} min ---")
            print(f"  {'|r_t| bps':>12}  {'meanNet':>8} {'hit%':>6} {'pooledN':>9} {'pairSignAgree':>13}")
            for lo, hi in ABS_BINS:
                pair_means = []
                pooled = []
                for p in PAIRS:
                    mid, bid, ask, r, t = data[p]
                    trig = np.isfinite(r) & (np.abs(r) >= lo) & (np.abs(r) < hi)
                    net = fade_net_bps(bid, ask, mid, t, trig, k, follow=follow)
                    v = net[np.isfinite(net)]
                    if len(v) >= 50:
                        pair_means.append(v.mean())
                        pooled.append(v)
                if not pooled:
                    continue
                allv = np.concatenate(pooled)
                sgn = np.sign(np.mean(pair_means))
                agree = np.mean([np.sign(m) == sgn for m in pair_means])
                label = f"{lo:.0f}-{hi:.0f}" if hi < 1e8 else f">{lo:.0f}"
                print(f"  {label:>12}  {allv.mean():+8.3f} {(allv>0).mean()*100:6.1f} "
                      f"{len(allv):>9} {agree:>13.2f}")
    print("\nNeedle = a (dir,size,hold) stratum with meanNet>0, hit>50%, pairSignAgree~1, real N.")


if __name__ == "__main__":
    main()

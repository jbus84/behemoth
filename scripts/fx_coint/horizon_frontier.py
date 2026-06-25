"""Map the reversion frontier: at what horizon does fading the prior period clear cost?

Hourly direction is dead; weekly mean-reversion survives. The edge turns on somewhere
between. Resample 1-min bars to TRUE time-bars at a ladder of horizons, test a simple
reversion strategy (position = -sign(prior return)) net of real round-trip spread,
pooled across 6 pairs with cross-pair sign agreement. Find the shortest horizon where
net mean > 0, sign-stable.

(Resampling 1-min TIME bars to coarser TIME bars is valid — the stale-bar artifact only
applies to resampling tick-COUNT bars.)

Usage:  uv run python scripts/fx_coint/horizon_frontier.py
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
# horizon label -> minutes
HORIZONS = {
    "1h": 60, "4h": 240, "320m": 320, "8h": 480, "12h": 720,
    "1d": 1440, "2d": 2880, "1w": 10080,
}


def load_min(sym):
    d = pl.read_parquet(f"data/tick_bars/{sym}_1m_flow.parquet").sort("bucket")
    mid = d["mid"].to_numpy().astype(np.float64)
    spr = ((d["ask"].to_numpy() - d["bid"].to_numpy()) / mid * 1e4).astype(np.float64)
    tmin = d["bucket"].to_numpy().astype("datetime64[m]").astype(np.int64)
    return mid, spr, tmin


def resample(mid, spr, tmin, h):
    """Last mid/spread per h-minute bin. Returns (bar_mid, bar_spr, bar_binstart)."""
    binid = tmin // h
    # last row in each bin = where next binid differs
    last = np.empty(len(binid), dtype=bool)
    last[-1] = True
    last[:-1] = binid[1:] != binid[:-1]
    return mid[last], spr[last], binid[last]


def main():
    print("=== HORIZON FRONTIER: reversion (fade prior period) net of real spread ===")
    print("    pooled 6 pairs; net>0 & signAgree~1 = a needle.\n")
    data = {p: load_min(p) for p in PAIRS}

    print(f"  {'horizon':>8} {'revIC':>7} {'grossRev':>9} {'cost':>6} {'netMean':>8} "
          f"{'hit%':>6} {'pooledN':>8} {'signAgree':>9}")
    for label, h in HORIZONS.items():
        pair_net_means = []
        pooled_net = []
        ics, grosses, costs = [], [], []
        for p in PAIRS:
            mid, spr, tmin = data[p]
            bmid, bspr, bbin = resample(mid, spr, tmin, h)
            if len(bmid) < 200:
                continue
            r = np.diff(np.log(bmid)) * 1e4              # period returns (bps)
            gap = np.diff(bbin)                          # bins between consecutive bars
            # mask returns spanning > ~1.5 periods (weekend/holiday) for sub-daily
            good = gap <= (2 if h < 1440 else 10_000)
            r = np.where(good, r, np.nan)
            prev, nxt = r[:-1], r[1:]
            m = np.isfinite(prev) & np.isfinite(nxt)
            if m.sum() < 100:
                continue
            prev, nxt = prev[m], nxt[m]
            ic = np.corrcoef(prev, nxt)[0, 1]            # <0 = reversion
            gross = -np.sign(prev) * nxt                 # fade prior period (bps)
            cost = np.nanmedian(bspr)                    # round-trip ~ one spread
            net = gross - cost
            ics.append(ic)
            grosses.append(gross.mean())
            costs.append(cost)
            pair_net_means.append(net.mean())
            pooled_net.append(net)
        if not pooled_net:
            continue
        allnet = np.concatenate(pooled_net)
        sgn = np.sign(np.mean(pair_net_means))
        agree = np.mean([np.sign(x) == sgn for x in pair_net_means])
        print(f"  {label:>8} {np.mean(ics):+7.3f} {np.mean(grosses):+9.3f} "
              f"{np.mean(costs):6.2f} {allnet.mean():+8.3f} {(allnet>0).mean()*100:6.1f} "
              f"{len(allnet):>8} {agree:>9.2f}")
    print("\nrevIC<0 = mean-reversion; grossRev = avg fade gross (bps); "
          "netMean = grossRev - cost, pooled.")


if __name__ == "__main__":
    main()

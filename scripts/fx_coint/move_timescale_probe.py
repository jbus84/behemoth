"""At what wall-clock timeframe does a big move actually happen?

The move is 100% one-bar at 100-tick, so the timescale = the DURATION of that bar.
Tick bars carry start (timestamp) and end (close_ts), so for the top-1% |return| bars
we measure how long ~N ticks took during the move (close_ts - timestamp), vs typical
bars. Done at 100-tick and 1000-tick. Also bps-per-second to characterise speed.

Usage: uv run python scripts/fx_coint/move_timescale_probe.py
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

PAIRS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]


def measure(suffix):
    durs_all, durs_evt, bps_evt, spd_evt = [], [], [], []
    for sym in PAIRS:
        d = pl.read_parquet(f"{DATA}/{sym}_{suffix}.parquet").sort("timestamp")
        mid = ((d["close_bid"].to_numpy() + d["close_ask"].to_numpy()) / 2)
        t0 = d["timestamp"].to_numpy().astype("datetime64[ns]").astype("int64")
        t1 = d["close_ts"].to_numpy().astype("datetime64[ns]").astype("int64")
        dur = (t1 - t0) / 1e9                                   # bar duration, seconds
        r = np.append(np.nan, np.diff(np.log(mid))) * 1e4       # bar return bps
        ok = np.isfinite(r) & (dur > 0) & (dur < 3600 * 6)
        thr = np.nanquantile(np.abs(r[ok]), 0.99)
        evt = ok & (np.abs(r) >= thr)
        durs_all.append(dur[ok])
        durs_evt.append(dur[evt])
        bps_evt.append(np.abs(r[evt]))
        spd_evt.append(np.abs(r[evt]) / np.maximum(dur[evt], 0.001))
    da = np.concatenate(durs_all)
    de = np.concatenate(durs_evt)
    be = np.concatenate(bps_evt)
    se = np.concatenate(spd_evt)

    def q(x, p):
        return np.nanquantile(x, p)

    print(f"\n[{suffix}]  bar duration seconds — typical vs top-1% move bars")
    print(f"   all bars   : median={np.median(da):7.1f}s  mean={np.mean(da):7.1f}s")
    print(f"   move bars  : median={np.median(de):7.1f}s  mean={np.mean(de):7.1f}s  "
          f"(p10={q(de, .1):.1f}s p90={q(de, .9):.1f}s)")
    print(f"   move size  : median={np.median(be):.1f} bps")
    print(f"   move SPEED : median={np.median(se):.2f} bps/sec  "
          f"(=> ~{np.median(be):.0f}bps over ~{np.median(de):.0f}s)")


def main():
    print("MOVE TIMESCALE — how long the one-bar move actually lasts (wall clock)")
    for suf in ("1000tick", "100tick"):
        measure(suf)


if __name__ == "__main__":
    main()

"""Per-pair x per-horizon reversion matrix — no cross-pair pooling.

Pooling across pairs hid the concentrated EURUSD weekly needle. So here we keep every
(pair, horizon) cell separate: fade prior period, net of real spread, report net mean
(bps) and a t-stat. A concentrated needle = a cell with net>0 and |t| large, even if
no other pair shares it. Covers short horizons (15m+) too.

Usage:  uv run python scripts/fx_coint/horizon_per_pair.py
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

from scripts.fx_coint.horizon_frontier import load_min, resample

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
HORIZONS = {"15m": 15, "30m": 30, "1h": 60, "2h": 120, "4h": 240, "320m": 320,
            "8h": 480, "12h": 720, "1d": 1440, "2d": 2880, "1w": 10080}


def cell(mid, spr, tmin, h):
    bmid, bspr, bbin = resample(mid, spr, tmin, h)
    if len(bmid) < 200:
        return None
    r = np.diff(np.log(bmid)) * 1e4
    gap = np.diff(bbin)
    good = gap <= (2 if h < 1440 else 10_000)
    r = np.where(good, r, np.nan)
    prev, nxt = r[:-1], r[1:]
    m = np.isfinite(prev) & np.isfinite(nxt)
    if m.sum() < 100:
        return None
    prev, nxt = prev[m], nxt[m]
    net = -np.sign(prev) * nxt - np.nanmedian(bspr)
    t = net.mean() / (net.std() + 1e-12) * np.sqrt(len(net))
    return net.mean(), t, len(net)


def main():
    print("=== PER-PAIR reversion (fade prior period) net of real spread ===")
    print("    cell = net bps  (t)   ;  * = net>0 & t>2  (a concentrated needle)\n")
    data = {p: load_min(p) for p in PAIRS}
    print(f"  {'horizon':>8} " + " ".join(f"{p[:6]:>14}" for p in PAIRS))
    for label, h in HORIZONS.items():
        cells = []
        for p in PAIRS:
            c = cell(*data[p], h)
            if c is None:
                cells.append(f"{'--':>14}")
            else:
                nm, t, n = c
                star = "*" if (nm > 0 and t > 2) else " "
                cells.append(f"{nm:+6.3f}({t:+4.1f}){star}")
        print(f"  {label:>8} " + " ".join(cells))
    print("\n  net>0 with t>2 (marked *) = a real per-pair needle pooling would hide.")


if __name__ == "__main__":
    main()

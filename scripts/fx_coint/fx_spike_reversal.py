"""Same extreme-spike reversal as crypto, but on FX hourly bars with REAL bid/ask.

Crypto found: fade top-0.5/1% |6h momentum| over 3h = broad reversal (but flat cost).
FX hourly bars have real bid/ask, so this is the apples-to-apples breadth check AND
the realistic-slippage test crypto lacked: enter the fade at t+1 crossing real spread,
exit at t+1+H crossing real spread. Net per pair + breadth.

Usage:  uv run python scripts/fx_coint/fx_spike_reversal.py
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

from scripts.fx_coint.hourly_multirocket_wfo import load_hourly

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
L, H = 6, 3  # 6h momentum, 3h fade hold


def trades(df, pct):
    mid = df["mid"].to_numpy(); bid = df["bid"].to_numpy(); ask = df["ask"].to_numpy()
    t = df["bucket"].to_numpy().astype("datetime64[h]").astype(np.int64)
    r = np.empty(len(mid)); r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    contig = np.empty(len(mid), bool); contig[0] = False
    contig[1:] = (t[1:] - t[:-1]) == 1
    r[~contig] = np.nan
    mom = pd.Series(r).rolling(L).sum().to_numpy()
    sgn = np.sign(mom); strength = np.abs(mom)
    n = len(mid)
    valid = np.isfinite(strength) & (sgn != 0)
    idx = np.where(valid)[0]
    idx = idx[(idx + 1 + H < n)]
    thr = np.nanquantile(strength[valid], 1 - pct / 100)
    idx = idx[strength[idx] >= thr]
    # require contiguous t .. t+1+H
    idx = idx[(t[idx + 1 + H] - t[idx]) == (1 + H)]
    # non-overlap
    picked, last = [], -10**9
    for i in idx:
        if i - last >= H:
            picked.append(i); last = i
    picked = np.array(picked)
    if len(picked) < 20:
        return np.array([])
    e, x = picked + 1, picked + 1 + H
    fade = -sgn[picked]              # fade the move
    m = mid[picked]
    prof = np.where(
        fade < 0,                    # short: sell bid_e, buy ask_x
        (bid[e] - ask[x]),
        (bid[x] - ask[e]),           # long: buy ask_e, sell bid_x
    ) / m * 1e4
    return prof


def main():
    print("=== FX EXTREME-SPIKE REVERSAL (fade top-pct |6h mom|, 3h, REAL bid/ask) ===")
    data = {p: load_hourly(p) for p in PAIRS}
    for pct in [1.0, 0.5]:
        print(f"\n### top {pct}% |momentum|, 3h fade, real-spread net ###")
        print(f"  {'pair':>8} {'netMean':>8} {'t':>5} {'N':>5}")
        means = []
        for p in PAIRS:
            v = trades(data[p], pct)
            if len(v) < 20:
                continue
            tt = v.mean() / (v.std() + 1e-12) * np.sqrt(len(v))
            means.append(v.mean())
            print(f"  {p:>8} {v.mean():+8.3f} {tt:+5.1f} {len(v):>5}")
        means = np.array(means)
        pos = (means > 0).mean() * 100
        bt = means.mean() / (means.std(ddof=1) + 1e-12) * np.sqrt(len(means))
        print(f"  BREADTH: {len(means)} pairs, {pos:.0f}% net-positive, "
              f"mean={means.mean():+.3f}bps, cross-pair t={bt:+.1f}")


if __name__ == "__main__":
    main()

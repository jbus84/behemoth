"""Extreme-spike reversal on FX hourly bars — GROSS vs NET breakdown.

Mirrors the construction from fx_spike_reversal.py exactly, then adds a
mid-to-mid gross line so we can isolate the cost squeeze.

Usage:  uv run python scripts/fx_coint/fx_spike_reversal_gross.py
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
    """Return dict with 'gross' and 'net' arrays for top-pct spikes."""
    mid = df["mid"].to_numpy()
    bid = df["bid"].to_numpy()
    ask = df["ask"].to_numpy()
    t = df["bucket"].to_numpy().astype("datetime64[h]").astype(np.int64)

    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    contig = np.empty(len(mid), bool)
    contig[0] = False
    contig[1:] = (t[1:] - t[:-1]) == 1
    r[~contig] = np.nan

    mom = pd.Series(r).rolling(L).sum().to_numpy()
    sgn = np.sign(mom)
    strength = np.abs(mom)
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
            picked.append(i)
            last = i
    picked = np.array(picked)
    if len(picked) < 20:
        return {"gross": np.array([]), "net": np.array([])}

    e, x = picked + 1, picked + 1 + H
    fade = -sgn[picked]  # fade the move
    m = mid[picked]

    net = np.where(
        fade < 0,
        (bid[e] - ask[x]),  # short: sell bid_e, buy ask_x
        (bid[x] - ask[e]),  # long:  buy ask_e, sell bid_x
    ) / m * 1e4

    gross = np.where(
        fade < 0,
        (mid[e] - mid[x]),  # short gross
        (mid[x] - mid[e]),  # long gross
    ) / m * 1e4

    return {"gross": gross, "net": net}


def main():
    print("=" * 65)
    print("FX EXTREME-SPIKE REVERSAL — GROSS (mid-to-mid) vs NET (bid/ask)")
    print("Construction: fade top-pct |6h momentum| over 3h, enter t+1, exit t+1+H")
    print("=" * 65)
    data = {p: load_hourly(p) for p in PAIRS}

    for pct in [1.0, 0.5]:
        print(f"\n### top {pct}% |momentum|  |  3h fade  |  N≥20 per pair ###")
        print(f"  {'pair':>8} {'grossMean':>9} {'netMean':>9} {'cost':>8} {'grossT':>6} {'netT':>6} {'N':>5}")
        gross_means, net_means = [], []
        for p in PAIRS:
            tr = trades(data[p], pct)
            g, n = tr["gross"], tr["net"]
            if len(g) < 20:
                print(f"  {p:>8} {'—':>9} {'—':>9} {'—':>8} {'—':>6} {'—':>6} {len(g):>5}")
                continue
            gm, nm = g.mean(), n.mean()
            gt = gm / (g.std() + 1e-12) * np.sqrt(len(g))
            nt = nm / (n.std() + 1e-12) * np.sqrt(len(n))
            gross_means.append(gm)
            net_means.append(nm)
            print(f"  {p:>8} {gm:+9.2f} {nm:+9.2f} {nm - gm:+8.2f} {gt:+6.1f} {nt:+6.1f} {len(g):>5}")

        gross_means = np.array(gross_means)
        net_means = np.array(net_means)
        if len(gross_means) == 0:
            continue

        pos_gross = (gross_means > 0).mean() * 100
        pos_net = (net_means > 0).mean() * 100
        bt_gross = gross_means.mean() / (gross_means.std(ddof=1) + 1e-12) * np.sqrt(len(gross_means))
        bt_net = net_means.mean() / (net_means.std(ddof=1) + 1e-12) * np.sqrt(len(net_means))

        print("\n  BREADTH SUMMARY:")
        print(f"    pairs evaluated : {len(gross_means)}/{len(PAIRS)}")
        print(f"    gross : {pos_gross:.0f}% pairs positive, mean={gross_means.mean():+.2f} bps, cross-pair t={bt_gross:+.1f}")
        print(f"    net   : {pos_net:.0f}% pairs positive, mean={net_means.mean():+.2f} bps, cross-pair t={bt_net:+.1f}")
        print(f"    cost  : mean drag {net_means.mean() - gross_means.mean():+.2f} bps")


if __name__ == "__main__":
    main()

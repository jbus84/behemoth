"""Weekend gap fade: FX Sunday open gaps partially revert intraday.

Classic hypothesis: weekend gaps (Fri close -> Sun 22:00 UTC open) partially close
over the next few hours. Uses real bid/ask for entry/exit.

Usage:
    uv run python scripts/fx_coint/weekend_gap_fade.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF"]
COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89}


def cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def gap_trades(sym: str, min_gap_bps: float = 5.0):
    """Find weekend gaps: Fri close -> next available bar after gap."""
    df = pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet").sort("bucket")
    df = df.with_columns(
        ((pl.col("ask") - pl.col("bid")) / pl.col("mid") * 1e4).alias("spr_bps")
    ).to_pandas()
    df["bucket"] = pd.to_datetime(df["bucket"])
    df = df.sort_values("bucket").reset_index(drop=True)

    mid = df["mid"].to_numpy()
    bid = df["bid"].to_numpy()
    ask = df["ask"].to_numpy()
    t = df["bucket"].to_numpy()
    c = cost(sym)

    # Find Friday close (last bar before weekend gap)
    # A gap = next bar is > 48h later (weekend)
    gaps = []
    for i in range(len(df) - 1):
        dt = (t[i+1] - t[i]).astype("timedelta64[s]").astype(int)
        if dt > 3600 * 24 * 2:  # gap > 2 days = weekend
            gaps.append(i)

    nets, sizes = [], []
    for i in gaps:
        # Friday close = mid[i], Sunday open = mid[i+1]
        gap_size = (np.log(mid[i+1]) - np.log(mid[i])) * 1e4
        if abs(gap_size) < min_gap_bps:
            continue
        # Fade: if gap up -> short; gap down -> long
        # Entry at t[i+1] (first bar after gap)
        # Hold for 1h = exit at t[i+1] + 1h or next available bar
        # Find bar 60min after open
        entry_t = t[i+1]
        exit_t = entry_t + np.timedelta64(60, "m")
        # Find nearest bar >= exit_t
        future = df[t > entry_t]
        if len(future) == 0:
            continue
        exit_idx = future.index[future["bucket"] >= exit_t]
        if len(exit_idx) == 0:
            continue
        j = exit_idx[0]
        # Real spread entry/exit
        if gap_size > 0:  # gap up -> short at bid_open, cover at ask_exit
            entry_px = bid[i+1]
            exit_px = ask[j]
        else:  # gap down -> long at ask_open, sell at bid_exit
            entry_px = ask[i+1]
            exit_px = bid[j]
        pnl = (exit_px - entry_px) / mid[i+1] * 1e4
        if gap_size > 0:
            pnl = -pnl  # short
        nets.append(pnl - c)
        sizes.append(abs(gap_size))

    return np.array(nets), np.array(sizes)


def main():
    print("=" * 80)
    print("WEEKEND GAP FADE — fade Sunday open gap over next 1h, real bid/ask")
    print("=" * 80)
    for sym in PAIRS:
        nets, sizes = gap_trades(sym, min_gap_bps=5.0)
        if len(nets) < 5:
            print(f"{sym}: too few gaps (n={len(nets)})")
            continue
        t, p = ttest_1samp(nets, 0)
        pos = (nets > 0).mean() * 100
        print(f"{sym:>8} n={len(nets):>3} meanNet={nets.mean():>+7.2f} t={t:>+5.2f} p={p:.3f} "
              f"hit={pos:.0f}% avgGap={sizes.mean():.1f}bps")

    # Pooled
    all_nets, all_sizes = [], []
    for sym in PAIRS:
        nets, sizes = gap_trades(sym, min_gap_bps=5.0)
        all_nets.extend(nets)
        all_sizes.extend(sizes)
    if len(all_nets) > 5:
        arr = np.array(all_nets)
        t, p = ttest_1samp(arr, 0)
        pos = (arr > 0).mean() * 100
        print(f"\n{'POOLED':>8} n={len(arr):>3} meanNet={arr.mean():>+7.2f} t={t:>+5.2f} p={p:.3f} "
              f"hit={pos:.0f}% avgGap={np.mean(all_sizes):.1f}bps")


if __name__ == "__main__":
    main()

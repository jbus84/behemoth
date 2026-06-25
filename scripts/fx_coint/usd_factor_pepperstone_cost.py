"""USD-factor residual fade at the user's REAL cost: Pepperstone cTrader Razor.

Honest bars (close_ts, no look-ahead) + the user's actual cost model:
  * Razor avg raw spread per pair (published, pips) -> bps via real avg mid
  * Commission $3.00/side/100k = $6 round-turn per 100k = 0.60 bps RT
Net per trade = mid-to-mid gross reversion - all-in RT cost (spread + commission).
Reports aggregate AND per-year net + t-stat per pair (robustness is the gate).

Usage: python usd_factor_pepperstone_cost.py [freq]   (default 30m)
"""

from __future__ import annotations

import sys

import numpy as np
import polars as pl
from usd_factor_residual_probe import PAIRS

FREQ = sys.argv[1] if len(sys.argv) > 1 else "30m"
TICK = sys.argv[2] if len(sys.argv) > 2 else "1000tick"  # 100tick = far finer time-bar build
TOP_PCT = 90
COMMISSION_RT_BPS = 0.60  # $3.00/side x2 / 100k notional

# Pepperstone Razor AVG raw spread, in pips (user-supplied)
RAZOR_SPREAD_PIPS = {
    "EURUSD": 0.1, "GBPUSD": 0.2, "AUDUSD": 0.1,
    "USDCAD": 0.5, "USDCHF": 0.4, "USDJPY": 0.3,
}
PIP_SIZE = {s: (0.01 if s == "USDJPY" else 0.0001) for s in RAZOR_SPREAD_PIPS}


def resampled(sym: str, freq: str) -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{sym}_{TICK}.parquet").with_columns(
        ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
        pl.col("close_ts").dt.truncate(freq).alias("bucket"),
    )
    return (
        df.sort("close_ts")
        .group_by("bucket")
        .agg(pl.col("mid").last().alias(f"mid_{sym}"))
        .sort("bucket")
    )


def main() -> None:
    syms = list(PAIRS)
    frames = [resampled(s, FREQ) for s in syms]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bucket", how="inner")
    df = df.drop_nulls().sort("bucket")
    print(f"{FREQ} close_ts bars: {df.height}  | cost = Razor avg spread + 0.60bps RT commission\n")

    mids = {s: df[f"mid_{s}"].to_numpy() for s in syms}
    R = np.column_stack([PAIRS[s] * np.diff(np.log(mids[s])) for s in syms])
    E = R - R.mean(axis=1, keepdims=True)
    years = df["bucket"].dt.year().to_numpy()
    yrs_all = sorted(set(years.tolist()))
    n_bars = len(df)

    # all-in cost per pair (bps)
    cost = {}
    for s in syms:
        avg_mid = float(np.nanmean(mids[s]))
        spr_bps = (RAZOR_SPREAD_PIPS[s] * PIP_SIZE[s] / avg_mid) * 1e4
        cost[s] = spr_bps + COMMISSION_RT_BPS

    print("  pair    spread_bps  all-in   n     net_bps    win%    t      pos-yrs")
    per_pair_year: dict[str, dict[int, float]] = {}
    for j, sy in enumerate(syms):
        mid = mids[sy]
        e = E[:, j]
        k = np.arange(len(e))
        entry_bar, exit_bar = k + 1, k + 2
        valid = exit_bar <= (n_bars - 1)
        absb = np.abs(e) * 1e4
        thr = np.percentile(absb[valid], TOP_PCT)
        sel = valid & (absb >= thr)
        pos = (-PAIRS[sy] * np.sign(e)).astype(int)
        eb, xb, p = entry_bar[sel], exit_bar[sel], pos[sel]
        gross = p * np.log(mid[xb] / mid[eb]) * 1e4
        net = gross - cost[sy]
        win = (net > 0).mean() * 100
        t = net.mean() / net.std() * np.sqrt(len(net)) if net.std() > 0 else 0.0
        yr = years[eb]
        per_pair_year[sy] = {y: net[yr == y].mean() for y in yrs_all if (yr == y).sum() >= 20}
        pos_yrs = sum(v > 0 for v in per_pair_year[sy].values())
        spr_only = cost[sy] - COMMISSION_RT_BPS
        print(f"  {sy}   {spr_only:6.2f}    {cost[sy]:5.2f}  {len(net):5d}  "
              f"{net.mean():+.3f}    {win:4.0f}  {t:+5.1f}    {pos_yrs}/{len(per_pair_year[sy])}")

    print("\nnet per year (at real Razor cost):")
    print("  pair    " + "  ".join(str(y) for y in yrs_all))
    for sy in syms:
        cells = [f"{per_pair_year[sy].get(y, float('nan')):+5.2f}" if y in per_pair_year[sy] else "  .  " for y in yrs_all]
        print(f"  {sy}  " + " ".join(cells))


if __name__ == "__main__":
    main()

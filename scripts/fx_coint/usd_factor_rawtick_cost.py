"""DEFINITIVE: USD-factor residual fade on TRUE raw-tick time bars + real Razor cost.

Reads the prebuilt last-tick-before-boundary bars (build_rawtick_timebars.py) so
there is ZERO bar-close staleness. Same spec as usd_factor_pepperstone_cost.py:
top-decile |1-factor residual| fade, enter k+1 / exit k+2, net = mid-to-mid gross
- (Razor avg spread + 0.60 bps RT commission). Per-year robustness.

Usage: python usd_factor_rawtick_cost.py [freq]   (15m | 30m, default 30m)
"""

from __future__ import annotations

import sys

import numpy as np
import polars as pl
from usd_factor_residual_probe import PAIRS

FREQ = sys.argv[1] if len(sys.argv) > 1 else "30m"
LIQUID = len(sys.argv) > 2 and sys.argv[2] == "liquid"  # restrict entry to 7-16 UTC
TOP_PCT = 90
COMMISSION_RT_BPS = 0.60
RAZOR_SPREAD_PIPS = {"EURUSD": 0.1, "GBPUSD": 0.2, "AUDUSD": 0.1, "USDCAD": 0.5, "USDCHF": 0.4, "USDJPY": 0.3}
PIP_SIZE = {s: (0.01 if s == "USDJPY" else 0.0001) for s in RAZOR_SPREAD_PIPS}


def load(sym: str, freq: str) -> pl.DataFrame:
    return (
        pl.read_parquet(f"data/tick_bars/{sym}_{freq}_raw.parquet")
        .select("bucket", pl.col("mid").alias(f"mid_{sym}"))
        .sort("bucket")
    )


def main() -> None:
    syms = list(PAIRS)
    df = load(syms[0], FREQ)
    for s in syms[1:]:
        df = df.join(load(s, FREQ), on="bucket", how="inner")
    df = df.drop_nulls().sort("bucket")
    print(f"{FREQ} RAW-TICK bars: {df.height}  | cost = Razor avg spread + 0.60bps RT commission\n")

    mids = {s: df[f"mid_{s}"].to_numpy() for s in syms}
    R = np.column_stack([PAIRS[s] * np.diff(np.log(mids[s])) for s in syms])
    E = R - R.mean(axis=1, keepdims=True)
    years = df["bucket"].dt.year().to_numpy()
    hours = df["bucket"].dt.hour().to_numpy()
    yrs_all = sorted(set(years.tolist()))
    n_bars = len(df)
    if LIQUID:
        print("  (entries restricted to 7-16 UTC liquid hours)")

    cost = {}
    for s in syms:
        avg_mid = float(np.nanmean(mids[s]))
        cost[s] = (RAZOR_SPREAD_PIPS[s] * PIP_SIZE[s] / avg_mid) * 1e4 + COMMISSION_RT_BPS

    print("  pair    all-in   n     gross    net_bps    win%    t      pos-yrs")
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
        if LIQUID:
            sel = sel & np.isin(hours[entry_bar.clip(max=n_bars - 1)], range(7, 17))
        pos = (-PAIRS[sy] * np.sign(e)).astype(int)
        eb, xb, p = entry_bar[sel], exit_bar[sel], pos[sel]
        gross = p * np.log(mid[xb] / mid[eb]) * 1e4
        net = gross - cost[sy]
        win = (net > 0).mean() * 100
        t = net.mean() / net.std() * np.sqrt(len(net)) if net.std() > 0 else 0.0
        yr = years[eb]
        per_pair_year[sy] = {y: net[yr == y].mean() for y in yrs_all if (yr == y).sum() >= 20}
        pos_yrs = sum(v > 0 for v in per_pair_year[sy].values())
        print(f"  {sy}   {cost[sy]:5.2f}  {len(net):6d}  {gross.mean():+.3f}   {net.mean():+.3f}    "
              f"{win:4.0f}  {t:+5.1f}    {pos_yrs}/{len(per_pair_year[sy])}")

    print("\nnet per year (TRUE raw-tick bars, real Razor cost):")
    print("  pair    " + "  ".join(str(y) for y in yrs_all))
    for sy in syms:
        cells = [f"{per_pair_year[sy].get(y, float('nan')):+5.2f}" if y in per_pair_year[sy] else "  .  " for y in yrs_all]
        print(f"  {sy}  " + " ".join(cells))


if __name__ == "__main__":
    main()

"""Close_ts variant of usd_factor_tickexact_fill — fixes the open-time
truncation look-ahead. ONLY change vs the original: bars are bucketed by
close_ts (the time the price is actually known), sorted by close_ts.

Everything else (top-decile fade, entry k+1 / exit k+2 at real bid/ask) is
identical, so any change in the result is attributable solely to the bar clock.
"""

from __future__ import annotations

import sys

import numpy as np
import polars as pl
from usd_factor_residual_probe import PAIRS

FREQ = sys.argv[1] if len(sys.argv) > 1 else "30m"
TOP_PCT = 90


def resampled(sym: str, freq: str) -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{sym}_1000tick.parquet").with_columns(
        ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
        pl.col("close_ts").dt.truncate(freq).alias("bucket"),  # <-- close_ts, not open timestamp
    )
    return (
        df.sort("close_ts")  # <-- sort by close_ts
        .group_by("bucket")
        .agg(
            pl.col("mid").last().alias(f"mid_{sym}"),
            pl.col("close_bid").last().alias(f"bid_{sym}"),
            pl.col("close_ask").last().alias(f"ask_{sym}"),
        )
        .sort("bucket")
    )


def main() -> None:
    syms = list(PAIRS)
    frames = [resampled(s, FREQ) for s in syms]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bucket", how="inner")
    df = df.drop_nulls().sort("bucket")
    print(f"{FREQ} bars: {df.height}  | CLOSE_TS bars | tick-exact = cross real bid/ask at bar close")

    mids = {s: df[f"mid_{s}"].to_numpy() for s in syms}
    bids = {s: df[f"bid_{s}"].to_numpy() for s in syms}
    asks = {s: df[f"ask_{s}"].to_numpy() for s in syms}
    R = np.column_stack([PAIRS[s] * np.diff(np.log(mids[s])) for s in syms])
    E = R - R.mean(axis=1, keepdims=True)
    years = df["bucket"].dt.year().to_numpy()
    yrs_all = sorted(set(years.tolist()))

    print("\n  pair    n     mid_gross   tickexact_net   spr_paid   win%   t")
    per_pair_year: dict[str, dict[int, float]] = {}
    n_bars = len(df)
    for j, sy in enumerate(syms):
        bid, ask, mid = bids[sy], asks[sy], mids[sy]
        e = E[:, j]
        k = np.arange(len(e))
        entry_bar = k + 1
        exit_bar = k + 2
        valid = exit_bar <= (n_bars - 1)
        absb = np.abs(e) * 1e4
        thr = np.percentile(absb[valid], TOP_PCT)
        sel = valid & (absb >= thr)
        pos = (-PAIRS[sy] * np.sign(e)).astype(int)
        eb, xb, p = entry_bar[sel], exit_bar[sel], pos[sel]
        ent_fill = np.where(p > 0, ask[eb], bid[eb])
        exit_fill = np.where(p > 0, bid[xb], ask[xb])
        te = p * np.log(exit_fill / ent_fill) * 1e4
        gross_mid = p * np.log(mid[xb] / mid[eb]) * 1e4
        spr_paid = (gross_mid - te).mean()
        win = (te > 0).mean() * 100
        t = te.mean() / te.std() * np.sqrt(len(te)) if te.std() > 0 else 0.0
        print(f"  {sy}  {len(te):5d}   {gross_mid.mean():+.3f}     {te.mean():+.3f}        {spr_paid:.3f}    {win:4.0f}  {t:+5.1f}")
        yr = years[eb]
        per_pair_year[sy] = {y: te[yr == y].mean() for y in yrs_all if (yr == y).sum() >= 20}

    print("\ntick-exact NET per year:")
    print("  pair    " + "  ".join(str(y) for y in yrs_all))
    for sy in syms:
        cells = [f"{per_pair_year[sy].get(y, float('nan')):+5.2f}" if y in per_pair_year[sy] else "  .  " for y in yrs_all]
        print(f"  {sy}  " + " ".join(cells))


if __name__ == "__main__":
    main()

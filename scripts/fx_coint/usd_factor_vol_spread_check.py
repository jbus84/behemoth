"""Is high residual-vol actually WIDE-spread, or just busier (tight-spread) sessions?

Tests the assumption behind the 'edge lives in the expensive regime' worry.
For the vol-z top-decile trades, compares the ACTUAL quoted spread in the
low-vol vs high-vol halves, the vol<->spread correlation, and the hour-of-day
structure (high vol in liquid London/NY hours = TIGHT spread = good).

Spread = full quoted (ask-bid)/mid (median within bar) = 1x round-trip taker
cost referenced to mid. Net here uses the ACTUAL per-trade spread, not a flat
commission, so high-vol trades are charged their real (possibly wider) spread.
Usage: python usd_factor_vol_spread_check.py [freq]   (default 30m)
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import polars as pl
from usd_factor_residual_probe import PAIRS

LAM = 0.94
FREQ = sys.argv[1] if len(sys.argv) > 1 else "30m"
WARMUP = 200


def resampled(sym: str, freq: str) -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{sym}_1000tick.parquet").with_columns(
        ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
        ((pl.col("close_ask") - pl.col("close_bid")) / ((pl.col("close_bid") + pl.col("close_ask")) / 2.0)).alias("rspr"),
        pl.col("timestamp").dt.truncate(freq).alias("bucket"),
    )
    return (
        df.sort("timestamp")
        .group_by("bucket")
        .agg(pl.col("mid").last().alias(f"mid_{sym}"), pl.col("rspr").median().alias(f"spr_{sym}"))
        .sort("bucket")
    )


def remove_k_pc(R: np.ndarray, k: int) -> np.ndarray:
    Rc = R - R.mean(axis=0)
    U, S, Vt = np.linalg.svd(Rc, full_matrices=False)
    return Rc - U[:, :k] @ np.diag(S[:k]) @ Vt[:k]


def ewma_vol(e: np.ndarray) -> np.ndarray:
    return np.sqrt(pd.Series(e).pow(2).shift(1).ewm(alpha=1 - LAM, adjust=False).mean().to_numpy())


def main() -> None:
    syms = list(PAIRS)
    frames = [resampled(s, FREQ) for s in syms]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bucket", how="inner")
    df = df.drop_nulls().sort("bucket")
    hod = df["bucket"].dt.hour().to_numpy()[1:-1]
    print(f"{FREQ} bars: {df.height}")

    rets = [PAIRS[s] * np.diff(np.log(df[f"mid_{s}"].to_numpy())) for s in syms]
    R = np.column_stack(rets)
    E = remove_k_pc(R, 2)
    SPR = np.column_stack([df[f"spr_{s}"].to_numpy()[1:] for s in syms]) * 1e4  # bps
    s = E[:-1]
    fwd = E[1:]
    cap = -np.sign(s) * fwd * 1e4
    spr = SPR[:-1]

    print("\nvol-z top-10% trades: spread(bps) + net-of-ACTUAL-spread, low-vol vs high-vol half")
    print("  pair   corr(vol,spr) | lowvol: spr  net | highvol: spr  net")
    for j, sy in enumerate(syms):
        e = s[:, j]
        sig = ewma_vol(E[:, j])[:-1]
        ok = np.isfinite(sig)
        ok[:WARMUP] = False
        c = float(np.corrcoef(sig[ok], spr[ok, j])[0, 1])
        z = np.abs(e / sig)
        ztop = ok & (z >= np.nanpercentile(np.where(ok, z, np.nan), 90))
        med = np.median(sig[ztop])
        lo = ztop & (sig < med)
        hi = ztop & (sig >= med)
        # net of ACTUAL quoted spread (1x round trip)
        lo_net = (cap[lo, j] - spr[lo, j]).mean()
        hi_net = (cap[hi, j] - spr[hi, j]).mean()
        print(f"  {sy}    {c:+.3f}      | {spr[lo,j].mean():5.2f} {lo_net:+.3f} | {spr[hi,j].mean():5.2f} {hi_net:+.3f}")

    print("\nhour-of-day (UTC): mean residual-vol(bps) and mean EURUSD spread(bps)")
    eu = syms.index("EURUSD")
    sig_eu = ewma_vol(E[:, eu])[:-1]
    vol_bps = np.abs(s[:, eu]) * 1e4
    print("  UTC  vol|move|  EURUSD_spr")
    for h in range(0, 24, 2):
        m = hod == h
        if m.sum() < 50:
            continue
        print(f"   {h:02d}    {vol_bps[m].mean():5.2f}     {spr[m,eu].mean():.3f}")


if __name__ == "__main__":
    main()

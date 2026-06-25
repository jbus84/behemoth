"""GARCH/vol-normalised dislocation selection for USD-factor residual reversion.

Does measuring dislocations in conditional-volatility z-scores (rather than raw
bps) sharpen reversion selection and de-concentrate the vol-regime mirages?

Conditional vol = causal EWMA (RiskMetrics lambda=0.94) of past squared residual
returns -- integrated-GARCH, fully look-ahead-free (sigma_t uses data <= t-1).
z_t = residual_return_t / sigma_t. Compare top-decile selection by |z| vs by raw
|residual| at commission cost, with per-year robustness and a low/high-vol split
(the tradeability tell: edge in CALM vol = tight spreads = survives real fills).

Usage: python usd_factor_volnorm_probe.py [freq]   (default 30m)
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import polars as pl
from usd_factor_residual_probe import PAIRS

COMMISSION_RT_BPS = 0.7
LAM = 0.94
FREQ = sys.argv[1] if len(sys.argv) > 1 else "30m"
WARMUP = 200


def resampled_mid(sym: str, freq: str) -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{sym}_1000tick.parquet").with_columns(
        ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
        pl.col("timestamp").dt.truncate(freq).alias("bucket"),
    )
    return df.sort("timestamp").group_by("bucket").agg(pl.col("mid").last().alias(f"mid_{sym}")).sort("bucket")


def remove_k_pc(R: np.ndarray, k: int) -> np.ndarray:
    Rc = R - R.mean(axis=0)
    U, S, Vt = np.linalg.svd(Rc, full_matrices=False)
    return Rc - U[:, :k] @ np.diag(S[:k]) @ Vt[:k]


def ewma_vol(e: np.ndarray) -> np.ndarray:
    """Causal EWMA conditional vol: sigma_t uses squared residuals up to t-1."""
    sig2 = pd.Series(e).pow(2).shift(1).ewm(alpha=1 - LAM, adjust=False).mean()
    return np.sqrt(sig2.to_numpy())


def main() -> None:
    syms = list(PAIRS)
    frames = [resampled_mid(s, FREQ) for s in syms]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bucket", how="inner")
    df = df.drop_nulls().sort("bucket")
    years = df["bucket"].dt.year().to_numpy()[1:]
    print(f"{FREQ} bars: {df.height}  cost={COMMISSION_RT_BPS}bps RT  EWMA lambda={LAM}")

    rets = [PAIRS[s] * np.diff(np.log(df[f"mid_{s}"].to_numpy())) for s in syms]
    R = np.column_stack(rets)
    E = remove_k_pc(R, 2)  # 2-factor residual
    s = E[:-1]
    fwd = E[1:]
    cap = -np.sign(s) * fwd * 1e4  # bps
    yrs = years[:-1]

    print("\nper pair: top-10% by RAW |move|   vs   top-10% by VOL-Z   (net@0.7, win%)")
    print("  pair       raw: net   win  |  volz: net   win  |  volz net: low-vol / high-vol half")
    for j, sy in enumerate(syms):
        e = s[:, j]
        sig = ewma_vol(E[:, j])[:-1]
        z = e / sig
        ok = np.isfinite(z)
        ok[:WARMUP] = False

        raw_top = ok & (np.abs(e) >= np.nanpercentile(np.where(ok, np.abs(e), np.nan), 90))
        z_top = ok & (np.abs(z) >= np.nanpercentile(np.where(ok, np.abs(z), np.nan), 90))

        rn = cap[raw_top, j].mean() - COMMISSION_RT_BPS
        rw = (cap[raw_top, j] > 0).mean() * 100
        zn = cap[z_top, j].mean() - COMMISSION_RT_BPS
        zw = (cap[z_top, j] > 0).mean() * 100

        # low/high vol split among the vol-z selected trades
        sig_sel = sig[z_top]
        med = np.median(sig_sel)
        lo = z_top & (sig < med)
        hi = z_top & (sig >= med)
        ln = cap[lo, j].mean() - COMMISSION_RT_BPS
        hn = cap[hi, j].mean() - COMMISSION_RT_BPS
        print(f"  {sy}    {rn:+.3f} {rw:4.0f}  |  {zn:+.3f} {zw:4.0f}  |  {ln:+.3f} / {hn:+.3f}")

    # per-year robustness of vol-z top-10%
    print("\nvol-z top-10% per-year NET @0.7:")
    print("  pair    " + "  ".join(str(y) for y in sorted(set(yrs.tolist()))))
    for j, sy in enumerate(syms):
        e = s[:, j]
        sig = ewma_vol(E[:, j])[:-1]
        z = e / sig
        ok = np.isfinite(z)
        ok[:WARMUP] = False
        z_top = ok & (np.abs(z) >= np.nanpercentile(np.where(ok, np.abs(z), np.nan), 90))
        cells = []
        for y in sorted(set(yrs.tolist())):
            m = z_top & (yrs == y)
            cells.append(f"{cap[m,j].mean()-COMMISSION_RT_BPS:+5.2f}" if m.sum() >= 20 else "  .  ")
        print(f"  {sy}  " + " ".join(cells))


if __name__ == "__main__":
    main()

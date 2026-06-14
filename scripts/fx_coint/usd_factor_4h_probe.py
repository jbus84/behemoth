"""USD-factor residual reversion at the 4-HOUR timeframe (PCA factor).

Steps UP from hourly: at 4h the reversion (if present) is slower and each move
is bigger, so a flat commission (~0.7bps RT) is a smaller fraction of gross.
Tests whether the edge improves. Sticks with PCA (1-factor EW == PC1, and a
2-factor remove-top-2-PC residual that helped at hourly).

Look-ahead guards: EW factor (no beta) for the 1-factor case; the 2-factor PCA
removal is full-sample (in-sample upper bound, same caveat as the hourly probe).
Cost = flat Pepperstone-style commission, frequency-independent.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from usd_factor_residual_probe import PAIRS

COMMISSION_RT_BPS = 0.7
FREQ = "4h"


def resampled_mid(sym: str, freq: str) -> pl.DataFrame:
    df = pl.read_parquet(f"data/tick_bars/{sym}_1000tick.parquet")
    df = df.with_columns(
        ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
        pl.col("timestamp").dt.truncate(freq).alias("bucket"),
    )
    return (
        df.sort("timestamp")
        .group_by("bucket")
        .agg(pl.col("mid").last().alias(f"mid_{sym}"))
        .sort("bucket")
    )


def remove_k_pc(R: np.ndarray, k: int) -> np.ndarray:
    if k == 0:
        return R
    Rc = R - R.mean(axis=0)
    U, S, Vt = np.linalg.svd(Rc, full_matrices=False)
    return Rc - U[:, :k] @ np.diag(S[:k]) @ Vt[:k]


def main() -> None:
    syms = list(PAIRS)
    frames = [resampled_mid(s, FREQ) for s in syms]
    df = frames[0]
    for f in frames[1:]:
        df = df.join(f, on="bucket", how="inner")
    df = df.drop_nulls().sort("bucket")
    print(f"{FREQ} bars: {df.height}  span {df['bucket'][0]} -> {df['bucket'][-1]}  cost={COMMISSION_RT_BPS}bps RT")

    rets = []
    for s in syms:
        mid = df[f"mid_{s}"].to_numpy()
        rets.append(PAIRS[s] * np.diff(np.log(mid)))
    R = np.column_stack(rets)
    years = df["bucket"].dt.year().to_numpy()[1:]  # aligned to returns

    Rc = R - R.mean(axis=0)
    _, S, _ = np.linalg.svd(Rc, full_matrices=False)
    var = S**2 / (S**2).sum()
    print("PC variance %:", np.round(var * 100, 1))

    for k in (1, 2):
        E = remove_k_pc(R, k)
        s = E[:-1]
        fwd = E[1:]
        cap = -np.sign(s) * fwd
        absb = np.abs(s) * 1e4
        # pooled reversion strength
        x, y = s[:-1].ravel(), s[1:].ravel()
        m = np.isfinite(x) & np.isfinite(y)
        corr = np.corrcoef(x[m], y[m])[0, 1]
        print(f"\n[{k}-factor residual]  pooled lag-1 corr {corr:+.4f}  | |move| p50={np.median(absb):.1f} p90={np.percentile(absb,90):.1f}bps")
        print("  pair      band(p75-95)  n     mean|mv|  gross    net    win%   |   top10% gross  net")
        for j, sy in enumerate(syms):
            a = absb[:, j]
            lo, hi = np.percentile(a, 75), np.percentile(a, 95)
            band = (a >= lo) & (a < hi)
            top = a >= np.percentile(a, 90)
            gb = cap[band, j].mean() * 1e4
            gt = cap[top, j].mean() * 1e4
            print(f"  {sy}   [{lo:5.1f},{hi:5.1f}]  {band.sum():5d}  {a[band].mean():6.1f}  {gb:+.3f}  {gb-COMMISSION_RT_BPS:+.3f}  {(cap[band,j]>0).mean()*100:4.0f}   |  {gt:+.3f}  {gt-COMMISSION_RT_BPS:+.3f}")

    # --- robustness of the 4h top-10% tail (2-factor), per-year net @0.7 + win% ---
    E2 = remove_k_pc(R, 2)
    s = E2[:-1]
    fwd = E2[1:]
    cap = -np.sign(s) * fwd
    absb = np.abs(s) * 1e4
    yrs = years[:-1]
    print("\n=== 2-factor top-10% tail: per-year NET @0.7 (robustness) ===")
    print("  pair     win%   " + "  ".join(str(y) for y in sorted(set(yrs.tolist()))))
    for j, sy in enumerate(syms):
        top = absb[:, j] >= np.percentile(absb[:, j], 90)
        win = (cap[top, j] > 0).mean() * 100
        cells = []
        for y in sorted(set(yrs.tolist())):
            m = top & (yrs == y)
            cells.append(f"{cap[m,j].mean()*1e4-COMMISSION_RT_BPS:+5.2f}" if m.sum() >= 10 else "   . ")
        print(f"  {sy}  {win:4.0f}   " + " ".join(cells))


if __name__ == "__main__":
    main()

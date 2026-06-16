"""STEP 1 PROBE: does a deviation in normalised quote flow (USD-factor residual)
predict forward price? Gross IC sweep across horizons, USD-factor vs residual,
per-pair + pooled, IS/OOS, with a price-residual baseline and BH-FDR. No strategy.

Pooled residual ICs subsample non-overlapping WITHIN each pair before pooling, so
the t-stat is not inflated by overlap or by striding across the pair-major layout.

Usage: python scripts/fx_coint/flow_factor_deviation_ic.py [proxy]   (flow_tick | flow_ofi)
"""

from __future__ import annotations

import sys
from math import erfc, sqrt

import numpy as np
import polars as pl

from scripts.fx_coint.flow_metrics import bh_fdr, deviation_tail_return, information_coefficient
from scripts.fx_coint.flow_proxies import causal_zscore
from scripts.fx_coint.usd_factor_residual_probe import PAIRS
from scripts.fx_coint.usd_flow_factor import orient, usd_factor_residual

PROXY = sys.argv[1] if len(sys.argv) > 1 else "flow_ofi"
HORIZONS = [1, 5, 15, 30, 60]
ZSPAN = 240  # 4h EWMA normalisation window in 1-min bars
IS_END = np.datetime64("2022-12-31")


def load() -> pl.DataFrame:
    df = None
    for s in PAIRS:
        d = pl.read_parquet(f"data/tick_bars/{s}_1m_flow.parquet").select(
            "bucket",
            causal_zscore(pl.col(PROXY), ZSPAN).alias(f"zf_{s}"),
            pl.col("mid").alias(f"mid_{s}"),
        )
        df = d if df is None else df.join(d, on="bucket", how="inner")
    return df.drop_nulls().sort("bucket")


def _p_from_t(t: float) -> float:
    return erfc(abs(t) / sqrt(2)) if np.isfinite(t) else 1.0


def pooled_nonoverlap(sig2d: np.ndarray, fwd2d: np.ndarray, tmask: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray]:
    """Concatenate per-pair non-overlapping (every h-th, within-regime) samples."""
    s_parts, f_parts = [], []
    for p in range(sig2d.shape[1]):
        s_parts.append(sig2d[tmask, p][::h])
        f_parts.append(fwd2d[tmask, p][::h])
    return np.concatenate(s_parts), np.concatenate(f_parts)


def main() -> None:
    syms = list(PAIRS)
    df = load()
    signs = np.array([PAIRS[s] for s in syms], dtype=float)
    zf = np.column_stack([df[f"zf_{s}"].to_numpy() for s in syms])
    logmid = np.column_stack([np.log(df[f"mid_{s}"].to_numpy()) for s in syms])
    times = df["bucket"].to_numpy().astype("datetime64[D]")
    is_mask = times <= IS_END

    oriented = orient(zf, signs)
    factor, residual = usd_factor_residual(oriented)

    # price-residual baseline: decompose oriented 1-bar price returns
    pr = np.vstack([np.full((1, len(syms)), np.nan), (logmid[1:] - logmid[:-1]) * signs[None, :]])
    _, price_res = usd_factor_residual(np.nan_to_num(pr))

    print(f"PROXY={PROXY}  bars={len(df)}  zspan={ZSPAN}  IS<= {IS_END}  "
          f"IS_bars={int(is_mask.sum())} OOS_bars={int((~is_mask).sum())}\n")
    print(f"  {'signal':10s} {'horizon':>7s} {'regime':>6s} {'n':>7s} {'IC':>8s} {'t':>6s} {'tail_bps':>9s}")

    pvals: list[float] = []
    labels: list[str] = []

    def emit(name: str, sig: np.ndarray, fwd: np.ndarray, h: int, tag: str) -> None:
        ic, t, n = information_coefficient(sig, fwd, horizon=1)  # already subsampled
        follow, _ = deviation_tail_return(sig, fwd, q=0.90)
        pvals.append(_p_from_t(t))
        labels.append(f"{name}|{tag}|h{h}")
        print(f"  {name:10s} {('h'+str(h)):>7s} {tag:>6s} {n:>7d} {ic:>+8.4f} {t:>+6.1f} {follow*1e4:>+9.2f}")

    for h in HORIZONS:
        fwd_pair = np.full_like(logmid, np.nan)
        fwd_pair[:-h] = (logmid[h:] - logmid[:-h]) * signs[None, :]
        fwd_basket = np.nanmean(fwd_pair, axis=1)
        for tag, mask in (("IS", is_mask), ("OOS", ~is_mask)):
            # FACTOR -> basket (1-D, non-overlap by stride within regime)
            emit("factor", factor[mask][::h], fwd_basket[mask][::h], h, tag)
            # RESIDUAL -> own pair (pooled, within-pair non-overlap)
            sr, fr = pooled_nonoverlap(residual, fwd_pair, mask, h)
            emit("residual", sr, fr, h, tag)
            # PRICE baseline residual
            sp, fp = pooled_nonoverlap(price_res, fwd_pair, mask, h)
            emit("price_res", sp, fp, h, tag)
        print()

    rej = bh_fdr(np.array(pvals), alpha=0.05)
    print(f"BH-FDR @0.05 across all {len(rej)} tests: {int(rej.sum())} significant\n")
    for lbl, p, r in sorted(zip(labels, pvals, rej, strict=True), key=lambda x: x[1])[:15]:
        print(f"  {'REJECT' if r else '  ----'}  {lbl:22s}  p={p:.2e}")


if __name__ == "__main__":
    main()

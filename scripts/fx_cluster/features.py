"""Causal, pair-normalized (pair, t) feature matrix.

Three blocks (spec section 4): temporal (own path), spatial (cross-currency via the
USD factor + residual), regime context. Every column uses only data <= t and is
z-scored with trailing-window stats so points from different pairs are comparable.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_cluster import config
from scripts.fx_cluster.causal import causal_zscore, ewma_vol, rolling_minmax_pos
from scripts.fx_cluster.factor import oriented_returns, residuals

ZWIN = 250          # trailing window for cross-pair-comparability z-scores
LOOKBACKS = (1, 4, 12, 24)


def _common_grid(bars: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Inner-join all pairs' mid on bucket so the spatial block is aligned."""
    out = None
    for p, df in bars.items():
        col = df.select("bucket", pl.col("mid").alias(f"mid_{p}")).sort("bucket")
        out = col if out is None else out.join(col, on="bucket", how="inner")
    return out.sort("bucket")


def build_features(bars: dict[str, pl.DataFrame]) -> tuple[pl.DataFrame, list[str]]:
    pairs = list(bars.keys())
    grid = _common_grid(bars)
    buckets = grid["bucket"].to_numpy()
    logret = {p: np.diff(np.log(grid[f"mid_{p}"].to_numpy()), prepend=np.nan) for p in pairs}
    for p in pairs:
        logret[p][0] = 0.0
    oriented = oriented_returns(logret)
    res = residuals(oriented)
    factor = sum(oriented[p] for p in pairs) / len(pairs)
    disp = np.vstack([res[p] for p in pairs]).std(axis=0)  # cross-sectional dispersion

    names: list[str] = []
    frames = []
    for p in pairs:
        mid = grid[f"mid_{p}"].to_numpy()
        r = logret[p]
        sigma = ewma_vol(r, config.EWMA_LAMBDA)
        sig_safe = np.where(sigma > 0, sigma, np.nan)
        feat = {"pair": p, "bucket": buckets}
        # temporal block
        for lb in LOOKBACKS:
            cum = np.concatenate([np.full(lb, np.nan), np.log(mid[lb:] / mid[:-lb])])
            feat[f"ret_{lb}h"] = causal_zscore(cum / (sig_safe * np.sqrt(lb)), ZWIN)
        feat["vol"] = causal_zscore(sigma, ZWIN)
        feat["vol_short"] = causal_zscore(sigma, 24)
        feat["range_pos_24"] = rolling_minmax_pos(mid, 24)
        feat["range_pos_120"] = rolling_minmax_pos(mid, 120)
        feat["trend"] = causal_zscore(
            np.sign(r).astype(float), 24)  # short-run sign persistence (zscored)
        # spatial block
        feat["resid"] = causal_zscore(res[p], ZWIN)
        feat["factor"] = causal_zscore(factor, ZWIN)
        feat["dispersion"] = causal_zscore(disp, ZWIN)
        rank = np.full(len(buckets), np.nan)
        stack = np.vstack([res[q] for q in pairs])
        order = stack.argsort(axis=0).argsort(axis=0)[pairs.index(p)]
        rank = order / (len(pairs) - 1)
        feat["xs_rank"] = rank
        # regime block
        hour = (buckets.astype("datetime64[h]").astype(int) % 24)
        feat["tod_sin"] = np.sin(2 * np.pi * hour / 24)
        feat["tod_cos"] = np.cos(2 * np.pi * hour / 24)
        frames.append(pl.DataFrame(feat))

    if not names:
        names = [c for c in frames[0].columns if c not in ("pair", "bucket")]
    # Drop the last row: the final bar's log-return uses mid[T]/mid[T-1]; the T+1
    # bar has not yet closed, so the return is incomplete.  Dropping it also
    # guarantees that mutating the final input bar cannot alter any returned feature.
    return pl.concat([f.head(f.height - 1) for f in frames]).sort(["bucket", "pair"]), names

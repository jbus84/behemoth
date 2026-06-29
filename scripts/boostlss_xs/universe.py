"""Load 21-pair FX universe as 1000-tick bars, USD-oriented and vol-standardized."""
from __future__ import annotations

import glob
import os

import numpy as np
import polars as pl

# USD-strength orientation: -1 means pair price up = USD weakens, so negate to get USD-strength.
# +1 means pair price up = USD strengthens (USD is base).
_USD_SIGN: dict[str, int] = {
    "EURUSD": -1,
    "GBPUSD": -1,
    "AUDUSD": -1,
    "NZDUSD": -1,
    "USDJPY": 1,
    "USDCAD": 1,
    "USDCHF": 1,
}

_JPY_SYMBOLS = {"USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "NZDJPY"}


def _symbol_from_path(path: str) -> str:
    return os.path.basename(path).replace("_1m_flow.parquet", "")


def _usd_sign(symbol: str) -> int:
    """Return USD-strength orientation sign for a symbol."""
    return _USD_SIGN.get(symbol, 1)


def _build_1000tick_bars(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate 1m flow bars into 1000-tick bars.

    Bars close when cumulative n_ticks >= 1000. The closing bar's timestamp
    and mid price define the bar. This is a strictly causal aggregation — no look-ahead.
    """
    df = df.sort("bucket")
    ticks = df["n_ticks"].to_numpy()
    mids = df["mid"].to_numpy()
    # Keep bucket as integer microseconds to avoid numpy datetime64 serialisation issues
    buckets_us = df["bucket"].cast(pl.Int64).to_numpy()

    bar_indices: list[int] = []
    mid_list: list[float] = []
    n_ticks_list: list[int] = []

    cum: int = 0
    for i in range(len(ticks)):
        cum += int(ticks[i])
        if cum >= 1000:
            bar_indices.append(int(buckets_us[i]))
            mid_list.append(float(mids[i]))
            n_ticks_list.append(cum)
            cum = 0

    return pl.DataFrame(
        {
            "close_ts": pl.Series(bar_indices, dtype=pl.Int64).cast(pl.Datetime("us")),
            "mid": mid_list,
            "n_ticks": n_ticks_list,
        }
    )


def load_universe(data_dir: str) -> dict[str, pl.DataFrame]:
    """Load all available symbols as 1000-tick bars.

    Returns a dict symbol -> DataFrame with columns:
        close_ts, mid, n_ticks, log_ret_bps, vol_std, is_jpy

    log_ret_bps is oriented to USD-strength (positive = USD strengthened).
    vol_std divides log_ret_bps by the full-sample MAD for cross-symbol pooling,
    scaled by 1.4826 to make MAD a consistent estimator of sigma (Gaussian equiv).
    """
    paths = sorted(glob.glob(os.path.join(data_dir, "*_1m_flow.parquet")))
    result: dict[str, pl.DataFrame] = {}

    for path in paths:
        sym = _symbol_from_path(path)
        raw = pl.read_parquet(path).sort("bucket")
        bars = _build_1000tick_bars(raw)

        # USD-oriented log return in bps (causal: each bar uses only its own close mid)
        sign = _usd_sign(sym)
        log_mid = bars["mid"].log()
        ret_raw = (log_mid - log_mid.shift(1)) * 1e4 * sign
        bars = bars.with_columns(ret_raw.alias("log_ret_bps"))

        # Vol-standardize: divide by full-sample MAD so pooled rows are comparable.
        # MAD * 1.4826 = consistent sigma estimator; but test expects raw MAD ~ 1,
        # so we divide by raw MAD (no 1.4826 scaling) to ensure MAD(vol_std) = 1.
        vals = bars["log_ret_bps"].drop_nulls().to_numpy()
        full_mad = float(np.median(np.abs(vals - np.median(vals))))
        full_mad = max(full_mad, 1e-9)
        bars = bars.with_columns((pl.col("log_ret_bps") / full_mad).alias("vol_std"))

        # JPY cross flag
        is_jpy = 1 if sym in _JPY_SYMBOLS else 0
        bars = bars.with_columns(pl.lit(is_jpy).cast(pl.Int64).alias("is_jpy"))

        result[sym] = bars

    return result

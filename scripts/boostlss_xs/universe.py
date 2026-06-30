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


def _build_tick_bars(df: pl.DataFrame, tick_size: int = 1000) -> pl.DataFrame:
    """Aggregate 1m flow bars into tick bars.

    tick_size=100  → one pass, returns 100-tick bars directly (close/mid only).
    tick_size=1000 → two-pass via 100-tick sub-bars, adds intrabar OHLC+path features.
    """
    df = df.sort("bucket")
    ticks = df["n_ticks"].to_numpy()
    mids = df["mid"].to_numpy()
    buckets_us = df["bucket"].cast(pl.Int64).to_numpy()

    # ── Pass 1: build 100-tick sub-bars ──────────────────────────────────────
    sub_ts: list[int] = []
    sub_mid: list[float] = []
    sub_ticks: list[int] = []
    cum = 0
    for i in range(len(ticks)):
        cum += int(ticks[i])
        if cum >= 100:
            sub_ts.append(int(buckets_us[i]))
            sub_mid.append(float(mids[i]))
            sub_ticks.append(cum)
            cum = 0

    sub_mids = np.array(sub_mid, dtype=np.float64)
    sub_ts_arr = np.array(sub_ts, dtype=np.int64)
    sub_ticks_arr = np.array(sub_ticks, dtype=np.int64)

    if tick_size == 100:
        if len(sub_mids) == 0:
            return pl.DataFrame({
                "close_ts": pl.Series([], dtype=pl.Datetime("us")),
                "mid": pl.Series([], dtype=pl.Float64),
                "n_ticks": pl.Series([], dtype=pl.Int64),
            })
        return pl.DataFrame({
            "close_ts": pl.Series(sub_ts_arr, dtype=pl.Int64).cast(pl.Datetime("us")),
            "mid": sub_mids.tolist(),
            "n_ticks": sub_ticks_arr.tolist(),
        })

    # ── Pass 2: group 10 sub-bars → 1000-tick bar ────────────────────────────
    _x = np.arange(10, dtype=np.float64)
    _x -= _x.mean()
    _xx = float(_x @ _x)

    n_sub = len(sub_mids)
    n_bars = n_sub // 10

    if n_bars == 0:
        return pl.DataFrame({
            "close_ts": pl.Series([], dtype=pl.Datetime("us")),
            "mid": pl.Series([], dtype=pl.Float64),
            "n_ticks": pl.Series([], dtype=pl.Int64),
            "bar_open": pl.Series([], dtype=pl.Float64),
            "bar_high": pl.Series([], dtype=pl.Float64),
            "bar_low": pl.Series([], dtype=pl.Float64),
            "intrabar_momentum": pl.Series([], dtype=pl.Float64),
            "intrabar_reversal": pl.Series([], dtype=pl.Float64),
        })

    idx = np.arange(n_bars) * 10
    windows = np.stack([sub_mids[i:i + 10] for i in idx])

    bar_open = windows[:, 0]
    bar_close = windows[:, 9]
    bar_high = windows.max(axis=1)
    bar_low = windows.min(axis=1)
    bar_range = bar_high - bar_low

    centred = windows - windows.mean(axis=1, keepdims=True)
    slopes = (centred @ _x) / _xx
    intrabar_momentum = np.where(bar_range > 1e-10, slopes / bar_range, 0.0)

    corr_num = (centred * _x[None, :]).sum(axis=1)
    corr_den = np.sqrt(((centred ** 2).sum(axis=1)) * _xx)
    intrabar_reversal = np.where(corr_den > 1e-12, corr_num / corr_den, 0.0)

    bar_ts = sub_ts_arr[idx + 9]
    bar_nticks = np.array([sub_ticks_arr[i:i + 10].sum() for i in idx], dtype=np.int64)

    return pl.DataFrame({
        "close_ts": pl.Series(bar_ts, dtype=pl.Int64).cast(pl.Datetime("us")),
        "mid": bar_close.tolist(),
        "n_ticks": bar_nticks.tolist(),
        "bar_open": bar_open.tolist(),
        "bar_high": bar_high.tolist(),
        "bar_low": bar_low.tolist(),
        "intrabar_momentum": intrabar_momentum.tolist(),
        "intrabar_reversal": intrabar_reversal.tolist(),
    })


def load_universe(data_dir: str, tick_size: int = 1000) -> dict[str, pl.DataFrame]:
    """Load all available symbols as tick bars.

    tick_size: 100 for 100-tick bars (close only), 1000 for 1000-tick bars
               with intrabar OHLC and path features (default).

    Returns a dict symbol -> DataFrame with columns:
        close_ts, mid, n_ticks, log_ret_bps, vol_std, is_jpy
        (plus bar_open/high/low/intrabar_* when tick_size=1000)

    log_ret_bps is oriented to USD-strength (positive = USD strengthened).
    vol_std divides log_ret_bps by the full-sample MAD for cross-symbol pooling.
    """
    paths = sorted(glob.glob(os.path.join(data_dir, "*_1m_flow.parquet")))
    result: dict[str, pl.DataFrame] = {}

    for path in paths:
        sym = _symbol_from_path(path)
        raw = pl.read_parquet(path).sort("bucket")
        bars = _build_tick_bars(raw, tick_size=tick_size)

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

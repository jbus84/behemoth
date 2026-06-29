"""Feature engineering for BoostLSS XS anomaly pipeline.

Two stages:
1. within_symbol_features(): per-symbol rolling features, strictly causal.
2. xs_features(): cross-sectional features via backward as-of join (added in Task 3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import kurtosis as scipy_kurtosis

# Ordered list of within-symbol feature column names (indices 0-16 in final matrix)
WITHIN_SYMBOL_FEATURES: list[str] = [
    "ret_5",
    "ret_10",
    "ret_20",
    "ret_50",
    "ret_100",
    "mad_vol_20",
    "mad_vol_50",
    "mom_rank_20",
    "mom_rank_50",
    "n_ticks_bar",
    "hour",
    "dow",
    "session",
    "vol_of_vol_20",
    "roll_kurt_50",
    "roll_kurt_100",
    "tail_count_100",
]


def _rolling_mad(arr: np.ndarray, window: int) -> np.ndarray:
    """Causal rolling 1.4826×MAD. Returns nan for rows with < window observations."""
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        w = arr[i - window + 1 : i + 1]
        out[i] = 1.4826 * float(np.median(np.abs(w - np.median(w))))
    return out


def _rolling_quantile_rank(arr: np.ndarray, window: int) -> np.ndarray:
    """Rank of arr[i] within arr[i-window+1:i+1], normalized to [0,1]."""
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        w = arr[i - window + 1 : i + 1]
        out[i] = float(np.sum(w <= arr[i])) / window
    return out


def _rolling_excess_kurtosis(arr: np.ndarray, window: int) -> np.ndarray:
    """Causal rolling excess kurtosis (Fisher definition, bias=False)."""
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        w = arr[i - window + 1 : i + 1]
        if np.std(w) < 1e-12:
            out[i] = 0.0
        else:
            out[i] = float(scipy_kurtosis(w, fisher=True, bias=False))
    return out


def _session_flag(hour: int) -> int:
    """Classify UTC hour into FX session: 0=Asia, 1=London, 2=Overlap, 3=NY."""
    if hour >= 22 or hour < 8:
        return 0  # Asia
    if 8 <= hour < 12:
        return 1  # London
    if 12 <= hour < 16:
        return 2  # London/NY overlap
    return 3  # NY


def _s(name: str, arr: np.ndarray) -> pl.Series:
    """Create a Polars Series from a numpy array, converting float NaN to null."""
    return pl.Series(name, arr).fill_nan(None)


def within_symbol_features(df: pl.DataFrame, symbol: str) -> pl.DataFrame:  # noqa: ARG001
    """Append 17 within-symbol feature columns to df. Strictly causal."""
    ret = df["log_ret_bps"].to_numpy()
    close_ts = df["close_ts"].to_numpy()
    n_ticks = df["n_ticks"].to_numpy()

    # Rolling return sums (causal: sum of exactly L most recent bars ending at i)
    cs = np.nancumsum(np.where(np.isnan(ret), 0.0, ret))
    for L, col in [
        (5, "ret_5"),
        (10, "ret_10"),
        (20, "ret_20"),
        (50, "ret_50"),
        (100, "ret_100"),
    ]:
        out = np.full(len(ret), np.nan)
        for i in range(L - 1, len(ret)):
            out[i] = cs[i] - (cs[i - L] if i - L >= 0 else 0.0)
        df = df.with_columns(_s(col, out))

    # Robust vol (rolling MAD)
    mad20 = _rolling_mad(ret, 20)
    mad50 = _rolling_mad(ret, 50)
    df = df.with_columns([_s("mad_vol_20", mad20), _s("mad_vol_50", mad50)])

    # Momentum quantile rank
    df = df.with_columns(
        [
            _s("mom_rank_20", _rolling_quantile_rank(ret, 20)),
            _s("mom_rank_50", _rolling_quantile_rank(ret, 50)),
        ]
    )

    # Bar activity: log(n_ticks + 1) to avoid log(0)
    df = df.with_columns(pl.Series("n_ticks_bar", np.log(n_ticks.astype(float) + 1.0)))

    # Time features from close_ts
    ts = pd.to_datetime(close_ts)
    # Ensure UTC-naive for .hour/.dayofweek access
    if ts.tz is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    hours = ts.hour.to_numpy().astype(np.int32)
    dows = ts.dayofweek.to_numpy().astype(np.int32)
    sessions = np.array([_session_flag(int(h)) for h in hours], dtype=np.int32)
    df = df.with_columns(
        [
            pl.Series("hour", hours),
            pl.Series("dow", dows),
            pl.Series("session", sessions),
        ]
    )

    # Vol-of-vol: rolling MAD of mad_vol_20
    df = df.with_columns(_s("vol_of_vol_20", _rolling_mad(mad20, 20)))

    # Rolling excess kurtosis
    df = df.with_columns(
        [
            _s("roll_kurt_50", _rolling_excess_kurtosis(ret, 50)),
            _s("roll_kurt_100", _rolling_excess_kurtosis(ret, 100)),
        ]
    )

    # Tail event count: count of bars in last 100 where |ret| > 3×mad_vol_20
    tail = np.full(len(ret), np.nan)
    for i in range(99, len(ret)):
        w_ret = np.abs(ret[i - 99 : i + 1])
        threshold = 3.0 * (mad20[i] if not np.isnan(mad20[i]) else 0.0)
        tail[i] = float(np.sum(w_ret > threshold))
    df = df.with_columns(_s("tail_count_100", tail))

    return df

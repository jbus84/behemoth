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


# Ordered XS feature column names (indices 17-29 in final matrix)
XS_FEATURES: list[str] = [
    "xs_rank",
    "xs_robust_z",
    "usd_factor_resid",
    "xs_iqr",
    "xs_iqr_trend",
    "xs_dispersion_zz",
    "loo_robust_z",
    "xs_kurt",
    "xs_bimodality",
    "pair_corr_mean",
    "mom_vol_interaction",
    "is_jpy",
    "symbol_code",
]

# Full ordered feature list (30 features)
ALL_FEATURES: list[str] = WITHIN_SYMBOL_FEATURES + XS_FEATURES

# Symbol encoding (sorted alphabetically, stable)


def _encode_symbol(symbols: list[str], target: str) -> int:
    """Return deterministic alphabetical integer code for target among all symbols."""
    sorted_syms = sorted(symbols)
    return sorted_syms.index(target)


def xs_features(universe: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Append cross-sectional features to each symbol using backward as-of join.

    For each target (symbol, bar) at close_ts=T, XS features are computed from
    the most recent bar for each peer with close_ts <= T (look-ahead-free).
    """
    sorted_uni = {sym: df.sort("close_ts") for sym, df in universe.items()}
    symbols = sorted(sorted_uni.keys())

    result: dict[str, pl.DataFrame] = {}

    for target_sym in symbols:
        target = sorted_uni[target_sym].clone()
        target_ret = target["log_ret_bps"].to_numpy()
        n = len(target)

        # Collect peer returns at each target bar via backward as-of join
        peer_rets: dict[str, np.ndarray] = {}
        for peer_sym in symbols:
            if peer_sym == target_sym:
                continue
            peer = sorted_uni[peer_sym].select(["close_ts", "log_ret_bps"])
            joined = target.select(["close_ts"]).join_asof(
                peer.rename({"log_ret_bps": f"_peer_{peer_sym}"}),
                on="close_ts",
                strategy="backward",
            )
            peer_rets[peer_sym] = joined[f"_peer_{peer_sym}"].to_numpy()

        peer_syms = [s for s in symbols if s != target_sym]
        peer_mat = np.column_stack([peer_rets[s] for s in peer_syms])  # (n, n_peers)

        # Full cross-section: (n, n_syms)
        full_mat = np.column_stack([target_ret, peer_mat])

        # XS rank of target (ordinal rank normalized [0,1])
        xs_rank = np.array(
            [
                (
                    np.nan
                    if np.isnan(target_ret[i])
                    else float(np.sum(~np.isnan(full_mat[i]) & (full_mat[i] <= target_ret[i])))
                    / max(float(np.sum(~np.isnan(full_mat[i]))), 1.0)
                )
                for i in range(n)
            ]
        )

        xs_robust_z = np.full(n, np.nan)
        xs_iqr = np.full(n, np.nan)
        xs_kurt = np.full(n, np.nan)
        xs_bimodality = np.full(n, np.nan)

        for i in range(n):
            row = full_mat[i]
            valid = row[~np.isnan(row)]
            if len(valid) < 3:
                continue
            med = float(np.median(valid))
            mad = 1.4826 * float(np.median(np.abs(valid - med)))
            xs_robust_z[i] = (target_ret[i] - med) / max(mad, 1e-9)
            q75, q25 = float(np.percentile(valid, 75)), float(np.percentile(valid, 25))
            xs_iqr[i] = q75 - q25
            if len(valid) >= 4:
                xs_kurt[i] = float(scipy_kurtosis(valid, fisher=True, bias=False))
                sk = float(np.mean(((valid - np.mean(valid)) / (np.std(valid) + 1e-9)) ** 3))
                xs_bimodality[i] = (sk**2 + 1.0) / (xs_kurt[i] + 3.0 + 1e-9)

        xs_iqr_trend = np.concatenate([[np.nan], np.diff(xs_iqr)])
        xs_dispersion_zz = _rolling_mad(xs_iqr, 100)

        loo_robust_z = np.full(n, np.nan)
        for i in range(n):
            peers = peer_mat[i]
            valid = peers[~np.isnan(peers)]
            if len(valid) < 2:
                continue
            med = float(np.median(valid))
            mad = 1.4826 * float(np.median(np.abs(valid - med)))
            loo_robust_z[i] = (target_ret[i] - med) / max(mad, 1e-9)

        # USD-factor residual: causal rolling OLS residual of target vs basket mean
        basket = np.nanmean(full_mat, axis=1)
        usd_factor_resid = np.full(n, np.nan)
        W = 250
        for i in range(W, n):
            yw = target_ret[i - W : i]
            xw = basket[i - W : i]
            valid_mask = ~(np.isnan(yw) | np.isnan(xw))
            if valid_mask.sum() < 50:
                continue
            xv, yv = xw[valid_mask], yw[valid_mask]
            beta = float(np.cov(xv, yv)[0, 1]) / max(float(np.var(xv)), 1e-12)
            alpha = float(np.mean(yv)) - beta * float(np.mean(xv))
            usd_factor_resid[i] = target_ret[i] - (alpha + beta * basket[i])

        # Rolling mean pairwise correlation (W=100)
        pair_corr_mean = np.full(n, np.nan)
        for i in range(100, n):
            block = full_mat[i - 100 : i]
            valid_cols = ~np.all(np.isnan(block), axis=0)
            if valid_cols.sum() < 2:
                continue
            with np.errstate(divide="ignore", invalid="ignore"):
                corr = np.corrcoef(block[:, valid_cols].T)
            if corr.shape[0] > 1:
                mask = ~np.eye(corr.shape[0], dtype=bool)
                pair_corr_mean[i] = float(np.nanmean(corr[mask]))

        mom_rank_20 = (
            target["mom_rank_20"].to_numpy()
            if "mom_rank_20" in target.columns
            else np.full(n, np.nan)
        )
        vol_of_vol_20 = (
            target["vol_of_vol_20"].to_numpy()
            if "vol_of_vol_20" in target.columns
            else np.full(n, np.nan)
        )
        mom_vol_interaction = mom_rank_20 * vol_of_vol_20

        sym_code = float(_encode_symbol(symbols, target_sym))

        target = target.with_columns(
            [
                pl.Series("xs_rank", xs_rank),
                pl.Series("xs_robust_z", xs_robust_z),
                pl.Series("usd_factor_resid", usd_factor_resid),
                pl.Series("xs_iqr", xs_iqr),
                pl.Series("xs_iqr_trend", xs_iqr_trend),
                pl.Series("xs_dispersion_zz", xs_dispersion_zz),
                pl.Series("loo_robust_z", loo_robust_z),
                pl.Series("xs_kurt", xs_kurt),
                pl.Series("xs_bimodality", xs_bimodality),
                pl.Series("pair_corr_mean", pair_corr_mean),
                pl.Series("mom_vol_interaction", mom_vol_interaction),
                pl.col("is_jpy").cast(pl.Float64),
                pl.Series("symbol_code", np.full(n, sym_code)),
            ]
        )
        result[target_sym] = target

    return result


def build_features(
    universe: dict[str, pl.DataFrame],
) -> tuple[np.ndarray, np.ndarray, list[str], list[str], np.ndarray]:
    """Stack all symbols into a single feature matrix, sorted by close_ts.

    Returns:
        X: float32 array of shape (valid_rows, 30)
        close_ts_arr: datetime64 array, time-sorted
        feature_names: list of 30 feature column names
        symbols_arr: symbol string per row, time-sorted
        sort_idx: np.intp array — use to reorder other per-row arrays to match time order
    """
    X_parts: list[np.ndarray] = []
    ts_parts: list[np.ndarray] = []
    sym_parts: list[list[str]] = []

    for sym in sorted(universe.keys()):
        df = universe[sym]
        mat = df.select(ALL_FEATURES).to_numpy().astype(np.float32)
        ts = df["close_ts"].to_numpy()

        # Drop rows with any NaN
        valid = ~np.any(np.isnan(mat), axis=1)
        X_parts.append(mat[valid])
        ts_parts.append(ts[valid])
        sym_parts.append([sym] * int(valid.sum()))

    X = np.vstack(X_parts)
    close_ts_arr = np.concatenate(ts_parts)
    symbols_arr_raw: list[str] = sum(sym_parts, [])

    # Sort by time so WFO fold boundaries are calendar-correct
    sort_idx = np.argsort(close_ts_arr, kind="stable")
    X = X[sort_idx]
    close_ts_arr = close_ts_arr[sort_idx]
    symbols_arr = [symbols_arr_raw[i] for i in sort_idx]

    return X, close_ts_arr, ALL_FEATURES, symbols_arr, sort_idx

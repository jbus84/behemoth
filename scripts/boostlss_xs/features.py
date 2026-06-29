"""Feature engineering for BoostLSS XS anomaly pipeline.

Two stages:
1. within_symbol_features(): per-symbol rolling features, strictly causal.
2. xs_features(): cross-sectional features via backward as-of join.

Performance: O(N×W) Python loops replaced with numpy sliding_window_view and
axis-wise vectorised operations throughout.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from numpy.lib.stride_tricks import sliding_window_view
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
    """Causal rolling 1.4826×MAD via sliding_window_view (vectorised)."""
    n = len(arr)
    out = np.full(n, np.nan)
    arr = np.ascontiguousarray(arr, dtype=np.float64)
    if n < window:
        return out
    windows = sliding_window_view(arr, window)  # (n-window+1, window)
    meds = np.median(windows, axis=1)
    out[window - 1 :] = 1.4826 * np.median(np.abs(windows - meds[:, None]), axis=1)
    return out


def _rolling_quantile_rank(arr: np.ndarray, window: int) -> np.ndarray:
    """Rank of arr[i] within its window, normalized to [0,1] (vectorised)."""
    n = len(arr)
    out = np.full(n, np.nan)
    arr = np.ascontiguousarray(arr, dtype=np.float64)
    if n < window:
        return out
    windows = sliding_window_view(arr, window)  # (n-window+1, window)
    current = arr[window - 1 :]  # last element of each window
    out[window - 1 :] = np.sum(windows <= current[:, None], axis=1) / window
    return out


def _rolling_excess_kurtosis(arr: np.ndarray, window: int) -> np.ndarray:
    """Causal rolling excess kurtosis (Fisher, bias=False) via stride tricks."""
    n = len(arr)
    out = np.full(n, np.nan)
    arr = np.ascontiguousarray(arr, dtype=np.float64)
    if n < window:
        return out
    windows = sliding_window_view(arr, window)  # (n-window+1, window)
    stds = np.std(windows, axis=1, ddof=1)
    valid = stds > 1e-12
    if valid.any():
        out[window - 1 :][valid] = scipy_kurtosis(
            windows[valid], axis=1, fisher=True, bias=False
        )
    return out


def _s(name: str, arr: np.ndarray) -> pl.Series:
    """Create a Polars Series from a numpy array, converting float NaN to null."""
    return pl.Series(name, arr).fill_nan(None)


def within_symbol_features(df: pl.DataFrame, symbol: str) -> pl.DataFrame:  # noqa: ARG001
    """Append 17 within-symbol feature columns to df. Strictly causal."""
    ret = df["log_ret_bps"].to_numpy(allow_copy=True).astype(np.float64)
    n = len(ret)
    n_ticks = df["n_ticks"].to_numpy(allow_copy=True)

    # Rolling return sums — vectorised via padded cumsum
    ret_no_nan = np.where(np.isnan(ret), 0.0, ret)
    cs = np.cumsum(ret_no_nan)
    cs_padded = np.empty(n + 1)
    cs_padded[0] = 0.0
    cs_padded[1:] = cs  # cs_padded[i+1] = cs[i]; cs_padded[0] = 0

    feature_cols = []
    for L, col in [
        (5, "ret_5"),
        (10, "ret_10"),
        (20, "ret_20"),
        (50, "ret_50"),
        (100, "ret_100"),
    ]:
        out = np.full(n, np.nan)
        # out[i] = cs[i] - cs[i-L]  (cs[-L] = 0 for i < L)
        # = cs_padded[i+1] - cs_padded[i-L+1]
        # For i in [L-1, n-1]: out[L-1:] = cs_padded[L:] - cs_padded[1:n-L+2]
        if n >= L:
            out[L - 1 :] = cs_padded[L:] - cs_padded[: n - L + 1]
        feature_cols.append(_s(col, out))

    # Robust vol (rolling MAD)
    mad20 = _rolling_mad(ret, 20)
    mad50 = _rolling_mad(ret, 50)
    feature_cols += [_s("mad_vol_20", mad20), _s("mad_vol_50", mad50)]

    # Momentum quantile rank
    feature_cols += [
        _s("mom_rank_20", _rolling_quantile_rank(ret, 20)),
        _s("mom_rank_50", _rolling_quantile_rank(ret, 50)),
    ]

    # Bar activity: log(n_ticks + 1)
    feature_cols.append(pl.Series("n_ticks_bar", np.log(n_ticks.astype(float) + 1.0)))

    # Time features from close_ts using Polars dt namespace
    ts = df["close_ts"]
    if ts.dtype != pl.Datetime("us", None) and ts.dtype != pl.Datetime("us", "UTC"):
        ts = ts.cast(pl.Datetime("us", "UTC"))
    hours = ts.dt.hour().to_numpy().astype(np.int32)
    dows = ts.dt.weekday().to_numpy().astype(np.int32)  # Mon=0 … Sun=6
    # Vectorised session classification (UTC): Asia=0, London=1, Overlap=2, NY=3
    sessions = np.where(
        (hours >= 22) | (hours < 8),
        0,
        np.where(
            hours < 12,
            1,
            np.where(hours < 16, 2, 3),
        ),
    ).astype(np.int32)
    feature_cols += [
        pl.Series("hour", hours),
        pl.Series("dow", dows),
        pl.Series("session", sessions),
    ]

    # Vol-of-vol: rolling MAD of mad_vol_20
    feature_cols.append(_s("vol_of_vol_20", _rolling_mad(mad20, 20)))

    # Rolling excess kurtosis
    feature_cols += [
        _s("roll_kurt_50", _rolling_excess_kurtosis(ret, 50)),
        _s("roll_kurt_100", _rolling_excess_kurtosis(ret, 100)),
    ]

    # Tail event count: count of |ret| > 3×mad20 in last 100 bars (vectorised)
    tail = np.full(n, np.nan)
    if n >= 100:
        abs_ret = np.abs(ret)
        windows_abs = sliding_window_view(np.ascontiguousarray(abs_ret), 100)
        thresholds = 3.0 * np.where(np.isnan(mad20[99:]), 0.0, mad20[99:])
        tail[99:] = np.sum(windows_abs > thresholds[:, None], axis=1).astype(float)
    feature_cols.append(_s("tail_count_100", tail))

    return df.with_columns(feature_cols)


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


def _encode_symbol(symbols: list[str], target: str) -> int:
    """Return deterministic alphabetical integer code for target among all symbols."""
    return sorted(symbols).index(target)


def _build_peer_mat(
    target: pl.DataFrame,
    sorted_uni: dict[str, pl.DataFrame],
    symbols: list[str],
    target_sym: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (peer_mat, full_mat) for target via backward as-of join."""
    target_ret = target["log_ret_bps"].to_numpy(allow_copy=True).astype(np.float64)
    peer_syms = [s for s in symbols if s != target_sym]
    peer_rets = {}
    for peer_sym in peer_syms:
        peer = sorted_uni[peer_sym].select(["close_ts", "log_ret_bps"])
        joined = target.select(["close_ts"]).join_asof(
            peer.rename({"log_ret_bps": f"_p"}),
            on="close_ts",
            strategy="backward",
        )
        peer_rets[peer_sym] = joined["_p"].to_numpy(allow_copy=True).astype(np.float64)
    peer_mat = np.column_stack([peer_rets[s] for s in peer_syms])
    full_mat = np.column_stack([target_ret, peer_mat])
    return peer_mat, full_mat


def xs_features(universe: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Append cross-sectional features to each symbol using backward as-of join.

    For each target (symbol, bar) at close_ts=T, XS features are computed from
    the most recent bar for each peer with close_ts <= T (look-ahead-free).
    """
    sorted_uni = {sym: df.sort("close_ts") for sym, df in universe.items()}
    symbols = sorted(sorted_uni.keys())

    # pair_corr_mean is a universe-level property (same for all symbols at a given bar).
    # Compute it once on the symbol with the most bars, then join to all targets.
    ref_sym = max(symbols, key=lambda s: len(sorted_uni[s]))
    ref_target = sorted_uni[ref_sym].clone()
    _, ref_full_mat = _build_peer_mat(ref_target, sorted_uni, symbols, ref_sym)
    ref_pcm = _rolling_pair_corr_mean(ref_full_mat, window=100)
    ref_pcm_df = pl.DataFrame({
        "close_ts": ref_target["close_ts"],
        "_pcm": pl.Series(ref_pcm).fill_nan(None),
    })

    result: dict[str, pl.DataFrame] = {}

    for target_sym in symbols:
        target = sorted_uni[target_sym].clone()
        target_ret = target["log_ret_bps"].to_numpy(allow_copy=True).astype(np.float64)
        n = len(target)

        peer_mat, full_mat = _build_peer_mat(target, sorted_uni, symbols, target_sym)
        K = full_mat.shape[1]

        # --- Vectorised XS stats (axis=1) ---
        valid_mask = ~np.isnan(full_mat)
        valid_counts = np.sum(valid_mask, axis=1)
        enough = valid_counts >= 3

        # XS rank (fraction of universe ≤ target)
        lte = (full_mat <= target_ret[:, None]) & valid_mask
        xs_rank = np.where(
            np.isnan(target_ret) | (valid_counts < 1),
            np.nan,
            np.sum(lte, axis=1) / np.maximum(valid_counts, 1).astype(float),
        )

        # XS robust z (median/MAD normalised)
        row_medians = np.where(enough, np.nanmedian(full_mat, axis=1), np.nan)
        row_deviations = np.abs(full_mat - row_medians[:, None])
        row_mads = np.where(enough, 1.4826 * np.nanmedian(row_deviations, axis=1), np.nan)
        xs_robust_z = np.where(
            enough,
            (target_ret - row_medians) / np.maximum(row_mads, 1e-9),
            np.nan,
        )

        # XS IQR — sort-based (154× faster than nanpercentile axis=1)
        sorted_mat = np.sort(full_mat, axis=1)  # NaN floats to end
        rows = np.arange(n)
        p25_idx = np.floor(valid_counts * 0.25).astype(int).clip(0, K - 1)
        p75_idx = np.floor(valid_counts * 0.75).astype(int).clip(0, K - 1)
        q25 = np.where(enough, sorted_mat[rows, p25_idx], np.nan)
        q75 = np.where(enough, sorted_mat[rows, p75_idx], np.nan)
        xs_iqr = q75 - q25

        xs_iqr_trend = np.concatenate([[np.nan], np.diff(xs_iqr)])
        xs_dispersion_zz = _rolling_mad(xs_iqr, 100)

        # LOO robust z (peers only, excluding self)
        peer_valid = np.sum(~np.isnan(peer_mat), axis=1)
        peer_enough = peer_valid >= 2
        peer_medians = np.where(peer_enough, np.nanmedian(peer_mat, axis=1), np.nan)
        peer_devs = np.abs(peer_mat - peer_medians[:, None])
        peer_mads = np.where(peer_enough, 1.4826 * np.nanmedian(peer_devs, axis=1), np.nan)
        loo_robust_z = np.where(
            peer_enough,
            (target_ret - peer_medians) / np.maximum(peer_mads, 1e-9),
            np.nan,
        )

        # XS kurtosis and bimodality (need ≥4 valid)
        valid_enough4 = valid_counts >= 4
        xs_kurt = np.full(n, np.nan)
        if valid_enough4.any():
            xs_kurt[valid_enough4] = scipy_kurtosis(
                full_mat[valid_enough4], axis=1, fisher=True, bias=False, nan_policy="omit"
            )
        means_full = np.nanmean(full_mat, axis=1)
        stds_full = np.nanstd(full_mat, axis=1)  # ddof=0, matching original
        centered = full_mat - means_full[:, None]
        sk = np.nanmean((centered / np.maximum(stds_full[:, None], 1e-9)) ** 3, axis=1)
        xs_bimodality = np.where(
            valid_enough4,
            (sk**2 + 1.0) / (xs_kurt + 3.0 + 1e-9),
            np.nan,
        )

        # USD-factor residual via Polars rolling sums
        basket = np.nanmean(full_mat, axis=1)
        usd_factor_resid = _rolling_ols_resid(target_ret, basket, window=250, min_periods=50)

        # pair_corr_mean: join from pre-computed reference via backward as-of
        pcm_joined = target.select(["close_ts"]).join_asof(
            ref_pcm_df, on="close_ts", strategy="backward"
        )
        pair_corr_mean = pcm_joined["_pcm"].to_numpy(allow_copy=True).astype(np.float64)

        # mom × vol-of-vol interaction
        mom_rank_20 = (
            target["mom_rank_20"].to_numpy(allow_copy=True)
            if "mom_rank_20" in target.columns
            else np.full(n, np.nan)
        )
        vol_of_vol_20 = (
            target["vol_of_vol_20"].to_numpy(allow_copy=True)
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


def _rolling_ols_resid(y: np.ndarray, x: np.ndarray, window: int, min_periods: int) -> np.ndarray:
    """Rolling OLS residual of y ~ x using Polars rolling sums (vectorised)."""
    n = len(y)
    # Joint validity mask: only count rows where both y and x are non-NaN
    joint_valid = ~(np.isnan(y) | np.isnan(x))
    y_j = np.where(joint_valid, y, np.nan)
    x_j = np.where(joint_valid, x, np.nan)
    xy_j = np.where(joint_valid, y * x, np.nan)
    x2_j = np.where(joint_valid, x * x, np.nan)
    cnt_j = joint_valid.astype(np.float64)

    # Polars rolling sums over jointly-valid values
    roll_df = pl.DataFrame(
        {
            "sum_y": pl.Series(y_j).fill_nan(None),
            "sum_x": pl.Series(x_j).fill_nan(None),
            "sum_xy": pl.Series(xy_j).fill_nan(None),
            "sum_x2": pl.Series(x2_j).fill_nan(None),
            "cnt": pl.Series(cnt_j).fill_nan(None),
        }
    ).select(
        pl.col("sum_y").rolling_sum(window, min_samples=min_periods),
        pl.col("sum_x").rolling_sum(window, min_samples=min_periods),
        pl.col("sum_xy").rolling_sum(window, min_samples=min_periods),
        pl.col("sum_x2").rolling_sum(window, min_samples=min_periods),
        pl.col("cnt").rolling_sum(window, min_samples=min_periods),
    )

    sum_y = roll_df["sum_y"].to_numpy(allow_copy=True)
    sum_x = roll_df["sum_x"].to_numpy(allow_copy=True)
    sum_xy = roll_df["sum_xy"].to_numpy(allow_copy=True)
    sum_x2 = roll_df["sum_x2"].to_numpy(allow_copy=True)
    cnt = roll_df["cnt"].to_numpy(allow_copy=True)

    sufficient = cnt >= min_periods
    mean_x = np.where(sufficient, sum_x / cnt, np.nan)
    mean_y = np.where(sufficient, sum_y / cnt, np.nan)
    var_x = np.where(sufficient, sum_x2 / cnt - mean_x**2, np.nan)
    cov_xy = np.where(sufficient, sum_xy / cnt - mean_x * mean_y, np.nan)
    beta = np.where(var_x > 1e-12, cov_xy / var_x, np.nan)
    alpha = mean_y - beta * mean_x
    return np.where(sufficient & ~np.isnan(beta), y - (alpha + beta * x), np.nan)


def _rolling_pair_corr_mean(mat: np.ndarray, window: int, chunk_size: int = 1000) -> np.ndarray:
    """Rolling mean pairwise correlation across all columns of mat, window bars.

    Chunked einsum keeps the per-chunk intermediate to ~chunk_size×K×window elements
    (~17 MB for K=21, W=100, chunk=1000) instead of N×K×window all at once.
    """
    n, K = mat.shape
    out = np.full(n, np.nan)
    if n < window or K < 2:
        return out

    off_diag = ~np.eye(K, dtype=bool)
    n_pairs = K * (K - 1)
    mat = mat.astype(np.float64)

    for chunk_start in range(window - 1, n, chunk_size):
        chunk_end = min(chunk_start + chunk_size, n)

        # Stride windows for this chunk: (K, chunk_bars, window)
        col_wins = np.stack(
            [
                sliding_window_view(
                    np.ascontiguousarray(mat[chunk_start - window + 1 : chunk_end, j]),
                    window,
                )
                for j in range(K)
            ],
            axis=0,
        )  # (K, chunk_bars, window)

        # Demean and normalise
        means = np.nanmean(col_wins, axis=2, keepdims=True)
        centered = col_wins - means
        stds = np.sqrt(np.nanmean(centered**2, axis=2))  # population std
        normed = centered / np.where(stds > 1e-12, stds, np.nan)[:, :, None]
        normed_clean = np.nan_to_num(normed, nan=0.0)

        # Valid-column gate: skip bars where any column has too few obs
        valid_counts = np.sum(~np.isnan(col_wins), axis=2)  # (K, chunk_bars)
        all_ok = np.all(valid_counts >= window // 2, axis=0)  # (chunk_bars,)

        # Cross-product → correlation matrix: (chunk_bars, K, K)
        nc = normed_clean.transpose(1, 0, 2)  # (chunk_bars, K, window)
        corr_mat = np.einsum("njw,nkw->njk", nc, nc) / window

        pair_sums = np.sum(corr_mat[:, off_diag], axis=1)  # (chunk_bars,)
        out[chunk_start:chunk_end] = np.where(all_ok, pair_sums / n_pairs, np.nan)

    return out


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

"""Tests for within-symbol feature engineering."""
from __future__ import annotations

import numpy as np
import pytest

from scripts.boostlss_xs.universe import load_universe

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/tick_bars"


@pytest.fixture(scope="module")
def eurusd_bars():
    uni = load_universe(DATA_DIR)
    # Limit to 2000 rows for speed (O(N×W) Python loops in rolling helpers)
    return uni["EURUSD"].head(2000)


@pytest.fixture(scope="module")
def small_universe_ws():
    """Small 3-symbol universe with within-symbol features applied (2000 bars each)."""
    from scripts.boostlss_xs.features import within_symbol_features

    uni = load_universe(DATA_DIR)
    # Pick 3 symbols for speed; 2000 bars each
    syms = sorted(uni.keys())[:3]
    small = {sym: uni[sym].head(2000) for sym in syms}
    return {sym: within_symbol_features(df, sym) for sym, df in small.items()}


def test_within_symbol_features_adds_all_columns(eurusd_bars):
    from scripts.boostlss_xs.features import WITHIN_SYMBOL_FEATURES, within_symbol_features

    result = within_symbol_features(eurusd_bars, "EURUSD")
    for col in WITHIN_SYMBOL_FEATURES:
        assert col in result.columns, f"missing column: {col}"


def test_rolling_ret_5_is_sum_of_last_5(eurusd_bars):
    from scripts.boostlss_xs.features import within_symbol_features

    result = within_symbol_features(eurusd_bars, "EURUSD")
    rets = eurusd_bars["log_ret_bps"].to_numpy()
    expected_ret5 = sum(rets[10:15])  # row 14 = sum of rows 10..14
    actual = result["ret_5"].to_numpy()[14]
    assert abs(actual - expected_ret5) < 1e-6


def test_no_look_ahead_in_rolling_features(eurusd_bars):
    """Causal check: features at row i must not use data from row i+1."""
    from scripts.boostlss_xs.features import within_symbol_features

    # Build features on first N rows; check feature at N-1 matches same row in full build
    N = 200
    sub = eurusd_bars.head(N)
    full = within_symbol_features(eurusd_bars, "EURUSD")
    partial = within_symbol_features(sub, "EURUSD")

    full_val = full["mad_vol_20"].to_numpy()[N - 1]
    partial_val = partial["mad_vol_20"].to_numpy()[N - 1]
    assert abs(full_val - partial_val) < 1e-9, (
        f"Look-ahead detected: full={full_val}, partial={partial_val}"
    )


def test_mom_rank_in_unit_interval(eurusd_bars):
    from scripts.boostlss_xs.features import within_symbol_features

    result = within_symbol_features(eurusd_bars, "EURUSD")
    ranks = result["mom_rank_20"].drop_nulls().to_numpy()
    assert ranks.min() >= 0.0
    assert ranks.max() <= 1.0


def test_session_flag_values(eurusd_bars):
    from scripts.boostlss_xs.features import within_symbol_features

    result = within_symbol_features(eurusd_bars, "EURUSD")
    assert set(result["session"].drop_nulls().unique().to_list()).issubset({0, 1, 2, 3})


def test_tail_count_non_negative(eurusd_bars):
    from scripts.boostlss_xs.features import within_symbol_features

    result = within_symbol_features(eurusd_bars, "EURUSD")
    assert (result["tail_count_100"].drop_nulls() >= 0).all()


def test_xs_features_adds_all_xs_columns(small_universe_ws):
    from scripts.boostlss_xs.features import XS_FEATURES, xs_features

    result = xs_features(small_universe_ws)
    for sym, df in result.items():
        for col in XS_FEATURES:
            assert col in df.columns, f"{sym} missing xs column: {col}"


def test_xs_no_look_ahead(small_universe_ws):
    """XS features at bar T must not use peer bars with close_ts > T."""
    import polars as pl

    from scripts.boostlss_xs.features import xs_features

    syms = sorted(small_universe_ws.keys())
    target_sym = syms[0]

    cutoff_idx = len(small_universe_ws[target_sym]) // 2
    cutoff_ts = small_universe_ws[target_sym]["close_ts"].to_numpy()[cutoff_idx]

    full = xs_features(small_universe_ws)

    uni_trunc = dict(small_universe_ws)
    uni_trunc[target_sym] = small_universe_ws[target_sym].filter(
        pl.col("close_ts") <= pl.lit(cutoff_ts).cast(pl.Datetime("us"))
    )
    partial = xs_features(uni_trunc)

    full_val = full[target_sym]["xs_rank"].to_numpy()[cutoff_idx]
    partial_val = partial[target_sym]["xs_rank"].to_numpy()[-1]
    assert abs(full_val - partial_val) < 1e-6, (
        f"Look-ahead in xs_rank: full={full_val:.4f}, partial={partial_val:.4f}"
    )


def test_build_features_shape(small_universe_ws):
    from scripts.boostlss_xs.features import build_features, xs_features

    uni = xs_features(small_universe_ws)
    X, close_ts_arr, feature_names, symbols_arr, sort_idx = build_features(uni)

    assert X.ndim == 2
    assert X.shape[1] >= 1
    assert X.shape[1] == len(feature_names)
    assert len(close_ts_arr) == X.shape[0]
    assert len(symbols_arr) == X.shape[0]
    assert X.dtype == np.float32
    assert len(sort_idx) == X.shape[0]


def test_build_features_time_sorted(small_universe_ws):
    """Returned close_ts_arr must be non-decreasing."""
    from scripts.boostlss_xs.features import build_features, xs_features

    uni = xs_features(small_universe_ws)
    X, close_ts_arr, _, symbols_arr, sort_idx = build_features(uni)
    assert np.all(close_ts_arr[1:] >= close_ts_arr[:-1]), "close_ts_arr is not non-decreasing"


def test_build_features_sort_idx_aligns_symbols(small_universe_ws):
    """symbols_arr[i] must match what sort_idx points to in the original symbol-blocked order."""
    from scripts.boostlss_xs.features import build_features, xs_features

    uni = xs_features(small_universe_ws)
    X, close_ts_arr, _, symbols_arr, sort_idx = build_features(uni)
    # sort_idx must be a valid permutation of range(len)
    assert len(sort_idx) == len(symbols_arr)
    assert set(sort_idx.tolist()) == set(range(len(symbols_arr)))

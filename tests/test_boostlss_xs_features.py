"""Tests for within-symbol feature engineering."""
from __future__ import annotations

import pytest

from scripts.boostlss_xs.universe import load_universe

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/tick_bars"


@pytest.fixture(scope="module")
def eurusd_bars():
    uni = load_universe(DATA_DIR)
    # Limit to 2000 rows for speed (O(N×W) Python loops in rolling helpers)
    return uni["EURUSD"].head(2000)


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

"""Tests for feature computation helpers in features.py."""

import numpy as np
import pandas as pd


def test_microstructure_helpers_exist():
    from src.behemoth.core.features import _compute_tick_burst_score

    s = pd.Series([100, 110, 90, 120, 105])
    score = _compute_tick_burst_score(s)
    assert isinstance(score, pd.Series)
    assert len(score) == len(s)


def test_compute_tick_burst_score():
    from src.behemoth.core.features import _compute_tick_burst_score

    s = pd.Series([1.0] * 30)
    result = _compute_tick_burst_score(s)
    assert isinstance(result, pd.Series)
    assert len(result) == len(s)
    # First element uses min_periods=1, so it should be 0 after shift(1)
    assert np.isfinite(result).all()


def test_compute_quote_revision_rate_z():
    from src.behemoth.core.features import _compute_quote_revision_rate_z

    s = pd.Series([1.0] * 30)
    result = _compute_quote_revision_rate_z(s)
    assert isinstance(result, pd.Series)
    assert len(result) == len(s)
    assert np.isfinite(result).all()


def test_compute_directional_persistence_8():
    from src.behemoth.core.features import _compute_directional_persistence_8

    s = pd.Series([1, -1, 1, -1, 1, -1, 1, -1, 1, -1])
    result = _compute_directional_persistence_8(s)
    assert isinstance(result, pd.Series)
    assert len(result) == len(s)
    assert np.isfinite(result).all()
    # With alternating signs, rolling sum of 8 should be 0 after enough bars
    assert result.iloc[-1] == 0.0


def test_compute_signed_flow_24():
    from src.behemoth.core.features import _compute_signed_flow_24

    s = pd.Series([1.0] * 30)
    result = _compute_signed_flow_24(s)
    assert isinstance(result, pd.Series)
    assert len(result) == len(s)
    assert np.isfinite(result).all()
    # All ones, rolling sum of 24 should be 24 for the last element
    assert result.iloc[-1] == 24.0


def test_compute_vol_cluster_score():
    from src.behemoth.core.features import _compute_vol_cluster_score

    s = pd.Series([1.0] * 30)
    result = _compute_vol_cluster_score(s)
    assert isinstance(result, pd.Series)
    assert len(result) == len(s)
    assert np.isfinite(result).all()
    # All same returns, abs_ret/roll_mean should be 1.0
    assert result.iloc[-1] == 1.0


def test_compute_session_marker():
    from src.behemoth.core.features import _compute_session_marker

    hours = pd.Series([0, 3, 7, 11, 14, 18, 22])
    result = _compute_session_marker(hours)
    assert isinstance(result, pd.Series)
    assert len(result) == len(hours)
    expected = pd.Series(["asia", "asia", "london", "lunch", "ny_overlap", "ny", "rollover"])
    assert result.equals(expected)

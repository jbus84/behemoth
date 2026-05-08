"""Tests for the extracted feature_parity diagnostic module."""

from __future__ import annotations

import pandas as pd
import pytest

from src.behemoth.diagnostics.feature_parity import (
    FEATURE_PARITY_COLUMNS,
    compare_feature_parity,
    parse_canonical_uid,
    parse_features_json,
)


def test_parse_features_json_tolerates_garbage() -> None:
    assert parse_features_json(None) == {}
    assert parse_features_json("") == {}
    assert parse_features_json("not json") == {}
    assert parse_features_json('{"x": 1.5, "y": "skip"}') == {"x": 1.5}


def test_parse_canonical_uid_trailing_k_convention() -> None:
    bar_ticks, horizon, barrier_pips = parse_canonical_uid(
        "oco|EURUSD|1000|h6|oco_first_touch_clean__all__k2"
    )
    assert (bar_ticks, horizon, barrier_pips) == (1000, 6, 2.0)


def test_compare_feature_parity_passes_when_values_match() -> None:
    live = pd.DataFrame(
        {
            "close_ts": pd.to_datetime(["2026-05-08T10:00:00Z"], utc=True),
            "candidate_uid": ["oco|EURUSD|100|h6|k2"],
            "features_json": ['{"range_pips": 8.5, "cost_est_pips": 0.4}'],
        }
    )
    recomputed = pd.DataFrame(
        {
            "close_ts": pd.to_datetime(["2026-05-08T10:00:00Z"], utc=True),
            "candidate_uid": ["oco|EURUSD|100|h6|k2"],
            "range_pips": [8.5],
            "cost_est_pips": [0.4],
        }
    )
    out = compare_feature_parity(
        live,
        recomputed,
        feature_columns=["range_pips", "cost_est_pips"],
        tolerance=1e-6,
    )
    assert list(out.columns) == FEATURE_PARITY_COLUMNS
    assert out.empty, f"expected no MISSING/MISMATCH rows, got: {out}"


def test_compare_feature_parity_normalizes_timezone_before_merge() -> None:
    """Regression: live close_ts came in as Europe/London tz-aware, recomputed
    close_ts as UTC. Pandas merge silently produced all-NaN live columns →
    all 7,504 rows reported as MISSING in the live diagnostic. Fix normalizes
    both sides to UTC before merging.
    """
    london = pd.Timestamp("2026-05-08T11:00:00", tz="Europe/London")  # 10:00 UTC
    utc = pd.Timestamp("2026-05-08T10:00:00", tz="UTC")  # same instant

    live = pd.DataFrame(
        {
            "close_ts": [london],
            "candidate_uid": ["oco|EURUSD|100|h6|k2"],
            "features_json": ['{"range_pips": 8.5}'],
        }
    )
    recomputed = pd.DataFrame(
        {
            "close_ts": [utc],
            "candidate_uid": ["oco|EURUSD|100|h6|k2"],
            "range_pips": [8.5],
        }
    )
    out = compare_feature_parity(
        live,
        recomputed,
        feature_columns=["range_pips"],
        tolerance=1e-6,
    )
    # Pre-fix, this would have returned a MISSING row because pandas treated
    # the two close_ts values as different keys despite representing the same
    # instant.
    assert out.empty, f"tz mismatch should not produce MISSING rows: {out}"


def test_compare_feature_parity_flags_real_mismatches() -> None:
    live = pd.DataFrame(
        {
            "close_ts": pd.to_datetime(["2026-05-08T10:00:00Z"], utc=True),
            "candidate_uid": ["uid"],
            "features_json": ['{"range_pips": 8.5}'],
        }
    )
    recomputed = pd.DataFrame(
        {
            "close_ts": pd.to_datetime(["2026-05-08T10:00:00Z"], utc=True),
            "candidate_uid": ["uid"],
            "range_pips": [9.0],
        }
    )
    out = compare_feature_parity(
        live,
        recomputed,
        feature_columns=["range_pips"],
        tolerance=0.1,
    )
    assert len(out) == 1
    assert out.iloc[0]["status"] == "MISMATCH"
    assert out.iloc[0]["abs_diff"] == pytest.approx(0.5)

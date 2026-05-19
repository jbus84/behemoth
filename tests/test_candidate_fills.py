from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.candidate_fills import candidate_id


def test_candidate_id_is_deterministic_and_12_hex():
    a = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "high_vol_cluster",
        {"horizon": 6, "barrier_pips": 2.0},
    )
    b = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "high_vol_cluster",
        {"horizon": 6, "barrier_pips": 2.0},
    )
    assert a == b
    assert len(a) == 12
    assert all(c in "0123456789abcdef" for c in a)


def test_candidate_id_differs_when_params_differ():
    a = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "r",
        {"horizon": 6, "barrier_pips": 2.0},
    )
    b = candidate_id(
        "EURUSD", "oco", "oco_first_touch", 1000, 6, "r",
        {"horizon": 6, "barrier_pips": 3.0},
    )
    assert a != b


def test_candidate_id_is_param_order_independent():
    a = candidate_id("EURUSD", "oco", "f", 1000, 6, "r", {"a": 1, "b": 2})
    b = candidate_id("EURUSD", "oco", "f", 1000, 6, "r", {"b": 2, "a": 1})
    assert a == b


def _full_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "close_ts": pd.to_datetime(
            ["2024-01-01T00:00:00Z", "2024-01-01T00:01:00Z",
             "2024-01-01T00:02:00Z"], utc=True),
        "tick_burst_score": [0.1, 0.2, 0.3],
        "directional_persistence_8": [1.0, 2.0, 3.0],
        "vol_cluster_score": [0.5, 0.6, 0.7],
        "session_marker": ["LON", "NY", "TOK"],
    })


def test_expand_fills_one_row_per_finite_entry():
    from scripts.candidate_fills import expand_fills

    frame = _full_frame()
    rows = expand_fills(
        frame, np.array([0, 2]), np.array([1.5, -0.5]),
        split="test", identity={"candidate_id": "abc", "symbol": "EURUSD"},
    )
    assert len(rows) == 2
    assert rows[0]["candidate_id"] == "abc"
    assert rows[0]["symbol"] == "EURUSD"
    assert rows[0]["split"] == "test"
    assert rows[0]["entry_index"] == 0
    assert rows[0]["entry_ts"] == frame["close_ts"].iloc[0]
    assert rows[0]["gross_pips"] == 1.5
    assert rows[0]["tick_burst_score"] == 0.1
    assert rows[0]["directional_persistence_8"] == 1.0
    assert rows[0]["vol_cluster_score"] == 0.5
    assert rows[0]["session_marker"] == "LON"
    assert rows[1]["entry_index"] == 2
    assert rows[1]["gross_pips"] == -0.5
    assert rows[1]["session_marker"] == "TOK"


def test_expand_fills_drops_non_finite_gross_keeping_alignment():
    from scripts.candidate_fills import expand_fills

    frame = _full_frame()
    # Middle fill has non-finite gross -> dropped; the other two survive
    # with their correct entry indices.
    rows = expand_fills(
        frame, np.array([0, 1, 2]), np.array([1.0, np.nan, 2.0]),
        split="train", identity={"candidate_id": "abc"},
    )
    assert [r["entry_index"] for r in rows] == [0, 2]
    assert [r["gross_pips"] for r in rows] == [1.0, 2.0]


def test_expand_fills_missing_feature_columns_degrade():
    from scripts.candidate_fills import expand_fills

    frame = pd.DataFrame({
        "close_ts": pd.to_datetime(["2024-01-01T00:00:00Z"], utc=True),
    })
    rows = expand_fills(
        frame, np.array([0]), np.array([1.0]),
        split="test", identity={"candidate_id": "abc"},
    )
    assert len(rows) == 1
    assert np.isnan(rows[0]["tick_burst_score"])
    assert np.isnan(rows[0]["directional_persistence_8"])
    assert np.isnan(rows[0]["vol_cluster_score"])
    assert rows[0]["session_marker"] == ""

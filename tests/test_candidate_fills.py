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


def test_write_candidate_fills_writes_parquet(tmp_path):
    from scripts.candidate_fills import write_candidate_fills

    rows = [
        {"candidate_id": "abc", "symbol": "EURUSD", "gross_pips": 1.0},
        {"candidate_id": "abc", "symbol": "EURUSD", "gross_pips": -0.5},
    ]
    path = write_candidate_fills(rows, tmp_path, "EURUSD")
    assert path.exists()
    assert path.parent.name == "candidate_fills"
    df = pd.read_parquet(path)
    assert len(df) == 2
    assert set(df["candidate_id"]) == {"abc"}


def test_write_candidate_fills_empty_writes_empty_schema_parquet(tmp_path):
    from scripts.candidate_fills import FILL_COLUMNS, write_candidate_fills

    path = write_candidate_fills([], tmp_path, "EURUSD")
    assert path.exists()
    df = pd.read_parquet(path)
    assert df.empty
    assert list(df.columns) == list(FILL_COLUMNS)


def test_write_candidate_fills_non_empty_uses_canonical_column_order(tmp_path):
    from scripts.candidate_fills import FILL_COLUMNS, write_candidate_fills

    # Row dict deliberately in NON-canonical key order.
    rows = [{
        "near_miss": False, "split": "test", "symbol": "EURUSD",
        "candidate_id": "abc", "family": "f", "library_type": "oco",
        "bar_ticks": 1000, "horizon": 6, "regime": "r", "entry_index": 0,
        "entry_ts": pd.Timestamp("2024-01-01T00:00:00Z"), "gross_pips": 1.0,
        "tick_burst_score": 0.1, "directional_persistence_8": 1.0,
        "vol_cluster_score": 0.5, "session_marker": "LON",
        "selection_pass": True,
    }]
    path = write_candidate_fills(rows, tmp_path, "EURUSD")
    df = pd.read_parquet(path)
    assert list(df.columns) == list(FILL_COLUMNS)


def test_candidate_fills_writer_chunked_matches_batch(tmp_path):
    from scripts.candidate_fills import (
        FILL_COLUMNS,
        CandidateFillsWriter,
        write_candidate_fills,
    )

    rows = [
        {
            "candidate_id": f"c{i}", "symbol": "EURUSD", "family": "f",
            "library_type": "oco", "bar_ticks": 1000, "horizon": 6,
            "regime": "r", "split": "test", "entry_index": i,
            "entry_ts": pd.Timestamp("2024-01-01T00:00:00Z"),
            "gross_pips": float(i), "tick_burst_score": 0.1,
            "directional_persistence_8": 1.0, "vol_cluster_score": 0.5,
            "session_marker": "LON",
            "selection_pass": bool(i % 2), "near_miss": False,
        }
        for i in range(5)
    ]
    batch_dir = tmp_path / "batch"
    chunk_dir = tmp_path / "chunked"
    batch_path = write_candidate_fills(rows, batch_dir, "EURUSD")
    with CandidateFillsWriter(chunk_dir, "EURUSD") as w:
        w.append(rows[:2])
        w.append(rows[2:])
    chunk_path = w.path
    batch_df = pd.read_parquet(batch_path).reset_index(drop=True)
    chunk_df = pd.read_parquet(chunk_path).reset_index(drop=True)
    assert list(chunk_df.columns) == list(FILL_COLUMNS)
    assert len(chunk_df) == len(batch_df) == 5
    assert chunk_df["gross_pips"].tolist() == batch_df["gross_pips"].tolist()
    assert chunk_df["candidate_id"].tolist() == batch_df["candidate_id"].tolist()


def test_candidate_fills_writer_empty_emits_canonical_schema(tmp_path):
    from scripts.candidate_fills import FILL_COLUMNS, CandidateFillsWriter

    with CandidateFillsWriter(tmp_path, "EURUSD") as w:
        pass
    df = pd.read_parquet(w.path)
    assert df.empty
    assert list(df.columns) == list(FILL_COLUMNS)

"""Tests for JForex outcome reconciliation."""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import duckdb
import pytest


def _write_locked_predictions(tmp: Path, symbol: str, rows: list[dict]) -> Path:
    """Write a minimal locked predictions parquet for testing."""
    con = duckdb.connect()
    cols = ", ".join(f"'{k}'" for k in rows[0])
    vals = ", ".join(
        "(" + ", ".join(
            f"'{v}'" if isinstance(v, str) else str(v) for v in r.values()
        ) + ")"
        for r in rows
    )
    con.execute(
        f"COPY (SELECT * FROM (VALUES {vals}) AS t({cols})) "
        f"TO '{tmp / f'{symbol.lower()}_oco_locked_predictions.parquet'}' (FORMAT PARQUET)"
    )
    return tmp


def _write_runtime_events(tmp: Path, symbol: str, prefix: str, rows: list[dict]) -> None:
    """Write a minimal runtime events CSV."""
    path = tmp / f"{symbol}_{prefix}_runtime_events.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["event_ts_utc", "symbol", "category", "event_name", "pass", "detail"],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def test_load_locked_predictions_filters_selected():
    from scripts.reconcile_jforex_outcomes import load_locked_predictions

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _write_locked_predictions(tmp, "EURUSD", [
            {"close_ts": "2025-07-01T00:00:00Z", "candidate_uid": "uid_a",
             "pred_prob": 0.6, "target_gross_pips": 3.5, "target_gross_pos": 1,
             "selected_exec": 1, "event_ordinal": 0},
            {"close_ts": "2025-07-01T01:00:00Z", "candidate_uid": "uid_a",
             "pred_prob": 0.4, "target_gross_pips": -1.2, "target_gross_pos": 0,
             "selected_exec": 0, "event_ordinal": 1},
        ])
        df = load_locked_predictions(tmp, "EURUSD")
        assert len(df) == 1
        assert df["target_gross_pips"].iloc[0] == 3.5


def test_load_runtime_events_counts_categories():
    from scripts.reconcile_jforex_outcomes import load_runtime_events

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _write_runtime_events(tmp, "EURUSD", "jforex", [
            {"event_ts_utc": "2025-07-01T00:00:00Z", "symbol": "EURUSD",
             "category": "signal", "event_name": "predict_cycle", "pass": "true",
             "detail": "prediction_count=5;selected_count=2;blocked_count=0;completed_bar_ticks=[100]"},
            {"event_ts_utc": "2025-07-01T00:01:00Z", "symbol": "EURUSD",
             "category": "execution", "event_name": "order_submitted", "pass": "true",
             "detail": "OCO_EURUSD_T100_H6:BUY"},
            {"event_ts_utc": "2025-07-01T00:01:01Z", "symbol": "EURUSD",
             "category": "execution", "event_name": "order_submitted", "pass": "true",
             "detail": "OCO_EURUSD_T100_H6:SELL"},
            {"event_ts_utc": "2025-07-01T00:02:00Z", "symbol": "EURUSD",
             "category": "execution", "event_name": "order_filled", "pass": "true",
             "detail": "OCO_EURUSD_T100_H6:BUY"},
        ])
        events = load_runtime_events(tmp, "EURUSD")
        assert events["predict_cycles"] == 1
        assert events["orders_submitted"] == 2
        assert events["orders_filled"] == 1


def test_compare_outcomes_pass():
    from scripts.reconcile_jforex_outcomes import compare_outcomes

    result = compare_outcomes(
        symbol="EURUSD",
        locked_count=217,
        locked_gross_pips_total=752.9,
        locked_win_rate=0.742,
        jforex_predict_cycles=200,
        jforex_selected_total=210,
        jforex_orders_submitted=4,
        jforex_execution_failures=0,
        jforex_lifecycle_failures=0,
    )
    assert result["signal_coverage_pass"] is True
    assert result["execution_clean_pass"] is True
    assert result["overall_pass"] is True


def test_compare_outcomes_fail_low_coverage():
    from scripts.reconcile_jforex_outcomes import compare_outcomes

    result = compare_outcomes(
        symbol="EURUSD",
        locked_count=217,
        locked_gross_pips_total=752.9,
        locked_win_rate=0.742,
        jforex_predict_cycles=50,
        jforex_selected_total=40,
        jforex_orders_submitted=0,
        jforex_execution_failures=0,
        jforex_lifecycle_failures=0,
    )
    assert result["signal_coverage_pass"] is False
    assert result["overall_pass"] is False

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
        jforex_submitted_group_count=200,  # 200/217 ≈ 92% > 80% → order_coverage_pass
    )
    assert result["signal_coverage_pass"] is True
    assert result["execution_clean_pass"] is True
    assert result["overall_pass"] is True


def test_load_locked_predictions_eval_window_filter():
    from scripts.reconcile_jforex_outcomes import load_locked_predictions
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Write 3 events: before window, in window, after window
        import pandas as pd
        df = pd.DataFrame([
            {"close_ts": pd.Timestamp("2025-07-06T23:59:00Z"), "candidate_uid": "uid_a",
             "pred_prob": 0.6, "target_gross_pips": 3.5, "target_gross_pos": 1,
             "selected_exec": 1, "event_ordinal": 0},
            {"close_ts": pd.Timestamp("2025-07-07T12:00:00Z"), "candidate_uid": "uid_b",
             "pred_prob": 0.7, "target_gross_pips": 2.5, "target_gross_pos": 1,
             "selected_exec": 1, "event_ordinal": 0},
            {"close_ts": pd.Timestamp("2025-07-09T00:00:01Z"), "candidate_uid": "uid_c",
             "pred_prob": 0.5, "target_gross_pips": 1.5, "target_gross_pos": 0,
             "selected_exec": 1, "event_ordinal": 0},
        ])
        df.to_parquet(str(tmp / "eurusd_oco_locked_predictions.parquet"), index=False)

        result = load_locked_predictions(
            tmp, "EURUSD",
            eval_start="2025-07-07T00:00:00Z",
            eval_end="2025-07-09T00:00:00Z",
        )
        assert len(result) == 1, f"Expected 1 event in window, got {len(result)}"
        assert result["candidate_uid"].iloc[0] == "uid_b"


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


from datetime import datetime, timezone


def test_parse_order_label_close_ts():
    from scripts.reconcile_jforex_outcomes import parse_order_label_close_ts

    label = "OCO_EURUSD_T100_H6_TS20250707162921_RIDNA_CID0448B71394297DAE_BUY"
    ts = parse_order_label_close_ts(label)
    assert ts == datetime(2025, 7, 7, 16, 29, 21, tzinfo=timezone.utc)


def test_parse_order_label_close_ts_missing():
    from scripts.reconcile_jforex_outcomes import parse_order_label_close_ts

    assert parse_order_label_close_ts("BAD_LABEL") is None


def test_load_runtime_events_order_matching():
    """order_submitted detail encodes close_ts; loader should extract group close timestamps."""
    from scripts.reconcile_jforex_outcomes import load_runtime_events
    import tempfile, csv

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Write a minimal runtime events CSV
        events_path = tmp / "EURUSD_local_jforex_runtime_events.csv"
        rows = [
            {"event_ts_utc": "2025-07-07T16:29:21Z", "symbol": "EURUSD",
             "category": "execution", "event_name": "order_submitted", "pass": "true",
             "detail": "OCO_EURUSD_T100_H6_TS20250707162921_RIDNA_CID001:OCO_EURUSD_T100_H6_TS20250707162921_RIDNA_CID001_BUY"},
            {"event_ts_utc": "2025-07-07T16:29:21Z", "symbol": "EURUSD",
             "category": "execution", "event_name": "order_submitted", "pass": "true",
             "detail": "OCO_EURUSD_T100_H6_TS20250707162921_RIDNA_CID001:OCO_EURUSD_T100_H6_TS20250707162921_RIDNA_CID001_SELL"},
            {"event_ts_utc": "2025-07-07T16:29:22Z", "symbol": "EURUSD",
             "category": "execution", "event_name": "trade_update_synced", "pass": "true",
             "detail": "LOCAL-1:CLOSED"},
        ]
        with open(events_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        events = load_runtime_events(tmp, "EURUSD")
        # Two legs submitted → 1 unique group close_ts
        assert events["submitted_group_close_ts_count"] == 1, f"Expected 1 unique group ts, got {events.get('submitted_group_close_ts_count')}"
        assert events["completed_group_count"] == 1, f"Expected 1 completed group, got {events.get('completed_group_count')}"


def test_compare_outcomes_per_event_coverage():
    """order_coverage_pass is still computed and returned, but does not gate overall_pass."""
    from scripts.reconcile_jforex_outcomes import compare_outcomes

    result = compare_outcomes(
        symbol="EURUSD",
        locked_count=100,
        locked_gross_pips_total=350.0,
        locked_win_rate=0.7,
        jforex_predict_cycles=200,
        jforex_selected_total=10,   # low signal coverage: 10/100 = 10%
        jforex_orders_submitted=200,
        jforex_execution_failures=0,
        jforex_lifecycle_failures=0,
        jforex_submitted_group_count=95,  # per-event: 95/100 = 95% > 80%
    )
    # order_coverage_pass is still computed correctly
    assert result["order_coverage_pass"] is True
    assert result["order_coverage_ratio"] == pytest.approx(0.95)
    # But signal_coverage is the gate: 10% < 80% → overall_pass is False
    assert result["signal_coverage_pass"] is False
    assert result["overall_pass"] is False


def test_compare_outcomes_signal_coverage_gates_not_order_coverage():
    """High signal coverage passes overall_pass even when order_coverage_pass is False."""
    from scripts.reconcile_jforex_outcomes import compare_outcomes

    result = compare_outcomes(
        symbol="EURUSD",
        locked_count=100,
        locked_gross_pips_total=350.0,
        locked_win_rate=0.7,
        jforex_predict_cycles=100,
        jforex_selected_total=90,    # 90% signal coverage → signal_coverage_pass=True
        jforex_orders_submitted=3,   # has_trades=True (OCO-blocked but some orders placed)
        jforex_execution_failures=0,
        jforex_lifecycle_failures=0,
        jforex_submitted_group_count=0,  # 0/100 = 0% order_coverage → order_coverage_pass=False
    )
    # order_coverage_ratio = 0/100 = 0.0 < 0.8 → order_coverage_pass = False (informational)
    assert result["order_coverage_pass"] is False
    # signal_coverage = 90% ≥ 80% AND has_trades=True → overall_pass = True
    assert result["signal_coverage_pass"] is True
    assert result["overall_pass"] is True


def test_overall_pass_uses_signal_coverage_not_order_coverage():
    """overall_pass should be True when signal_coverage >= threshold, regardless of order count."""
    from scripts.reconcile_jforex_outcomes import compare_outcomes

    # High signal coverage (95%), zero orders placed (blocked by open positions)
    result = compare_outcomes(
        symbol="GBPUSD",
        locked_count=100,
        locked_gross_pips_total=300.0,
        locked_win_rate=0.72,
        jforex_predict_cycles=500,
        jforex_selected_total=95,
        jforex_orders_submitted=2,
        jforex_execution_failures=0,
        jforex_lifecycle_failures=0,
        jforex_submitted_group_count=2,  # only 2 orders placed (blocked) → order_coverage=2%
    )
    assert result["signal_coverage_ratio"] == pytest.approx(0.95)
    assert result["signal_coverage_pass"] is True
    assert result["order_coverage_ratio"] == pytest.approx(0.02)
    assert result["order_coverage_pass"] is False   # still informational
    # FAILS with old code (uses order_coverage_pass as gate):
    assert result["overall_pass"] is True           # passes because signal_coverage_pass=True


def test_reconcile_writes_per_symbol_csv(tmp_path):
    from scripts.reconcile_jforex_outcomes import write_per_symbol_summaries
    import pandas as pd

    results = [
        {"symbol": "EURUSD", "overall_pass": True, "order_coverage_ratio": 0.95,
         "execution_clean_pass": True, "has_trades": True},
        {"symbol": "GBPUSD", "overall_pass": False, "order_coverage_ratio": 0.5,
         "execution_clean_pass": True, "has_trades": True},
    ]
    write_per_symbol_summaries(results, out_dir=tmp_path)

    eurusd_csv = tmp_path / "EURUSD_local_jforex_outcome_parity_summary.csv"
    assert eurusd_csv.exists(), f"Expected {eurusd_csv} to exist"
    df = pd.read_csv(eurusd_csv)
    assert "jforex_outcome_parity_pass" in df.columns, "Missing jforex_outcome_parity_pass column"
    # overall_pass is True, so jforex_outcome_parity_pass should also be truthy
    val = df["jforex_outcome_parity_pass"].iloc[0]
    assert val in (True, "True", "true", 1), f"Unexpected value: {val}"

    gbpusd_csv = tmp_path / "GBPUSD_local_jforex_outcome_parity_summary.csv"
    assert gbpusd_csv.exists(), f"Expected {gbpusd_csv} to exist"

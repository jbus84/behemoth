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


def test_compare_outcomes_zero_lock_passes_when_runtime_is_clean_noop():
    from scripts.reconcile_jforex_outcomes import compare_outcomes

    result = compare_outcomes(
        symbol="EURUSD",
        locked_count=0,
        locked_gross_pips_total=0.0,
        locked_win_rate=0.0,
        jforex_predict_cycles=34,
        jforex_selected_total=0,
        jforex_orders_submitted=0,
        jforex_execution_failures=0,
        jforex_lifecycle_failures=0,
        jforex_submitted_group_count=0,
    )
    assert result["signal_coverage_pass"] is True
    assert result["has_trades"] is False
    assert result["overall_pass"] is True


def test_compare_outcomes_zero_lock_fails_on_unexpected_runtime_activity():
    from scripts.reconcile_jforex_outcomes import compare_outcomes

    result = compare_outcomes(
        symbol="EURUSD",
        locked_count=0,
        locked_gross_pips_total=0.0,
        locked_win_rate=0.0,
        jforex_predict_cycles=34,
        jforex_selected_total=1,
        jforex_orders_submitted=0,
        jforex_execution_failures=0,
        jforex_lifecycle_failures=0,
        jforex_submitted_group_count=0,
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


def test_parse_predict_cycle_close_ts():
    from scripts.reconcile_jforex_outcomes import parse_predict_cycle_close_ts

    ts = parse_predict_cycle_close_ts(
        "prediction_count=5;selected_count=2;blocked_count=0;"
        "close_ts=2025-07-07T12:00:00Z;completed_bar_ticks=[100]"
    )
    assert ts == datetime(2025, 7, 7, 12, 0, 0, tzinfo=timezone.utc)


def test_load_runtime_events_ignores_extra_predict_cycle_diagnostics(tmp_path):
    from scripts.reconcile_jforex_outcomes import load_runtime_events

    _write_runtime_events(tmp_path, "EURUSD", "jforex", [
        {
            "event_ts_utc": "2026-03-22T10:00:00Z",
            "symbol": "EURUSD",
            "category": "signal",
            "event_name": "predict_cycle",
            "pass": "true",
            "detail": (
                "prediction_count=4;selected_count=1;blocked_count=3;"
                "blocked_reasons=entries_paused,active_candidate_lifecycle,risk_blocked;"
                "close_ts=2026-02-07T12:00:00Z;completed_bar_ticks=[100]"
            ),
        }
    ])

    events = load_runtime_events(tmp_path, "EURUSD")
    assert events["predict_cycles"] == 1
    assert events["selected_count_total"] == 1


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


def test_load_runtime_events_filters_eval_window_using_replay_close_ts(tmp_path):
    from scripts.reconcile_jforex_outcomes import load_runtime_events

    _write_runtime_events(tmp_path, "EURUSD", "jforex", [
        {
            "event_ts_utc": "2026-03-22T10:00:00Z",
            "symbol": "EURUSD",
            "category": "signal",
            "event_name": "predict_cycle",
            "pass": "true",
            "detail": (
                "prediction_count=4;selected_count=2;blocked_count=0;"
                "close_ts=2026-02-07T12:00:00Z;completed_bar_ticks=[100]"
            ),
        },
        {
            "event_ts_utc": "2026-03-22T10:05:00Z",
            "symbol": "EURUSD",
            "category": "signal",
            "event_name": "predict_cycle",
            "pass": "true",
            "detail": (
                "prediction_count=3;selected_count=1;blocked_count=0;"
                "close_ts=2026-02-10T12:00:00Z;completed_bar_ticks=[100]"
            ),
        },
        {
            "event_ts_utc": "2026-03-22T10:00:05Z",
            "symbol": "EURUSD",
            "category": "execution",
            "event_name": "order_submitted",
            "pass": "true",
            "detail": (
                "OCO_EURUSD_T100_H6_TS20260207120000_RIDNA_CID001:"
                "OCO_EURUSD_T100_H6_TS20260207120000_RIDNA_CID001_BUY"
            ),
        },
        {
            "event_ts_utc": "2026-03-22T10:05:05Z",
            "symbol": "EURUSD",
            "category": "execution",
            "event_name": "order_submitted",
            "pass": "true",
            "detail": (
                "OCO_EURUSD_T100_H6_TS20260210120000_RIDNA_CID002:"
                "OCO_EURUSD_T100_H6_TS20260210120000_RIDNA_CID002_BUY"
            ),
        },
    ])

    events = load_runtime_events(
        tmp_path,
        "EURUSD",
        eval_start="2026-02-07T00:00:00Z",
        eval_end="2026-02-09T00:00:00Z",
    )
    assert events["predict_cycles"] == 1
    assert events["selected_count_total"] == 2
    assert events["orders_submitted"] == 1
    assert events["submitted_group_close_ts_count"] == 1


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


def test_reconcile_per_symbol_csv_includes_evaluated_at_utc(tmp_path):
    """Per-symbol output CSV must propagate evaluated_at_utc from the result dict."""
    from scripts.reconcile_jforex_outcomes import write_per_symbol_summaries
    import pandas as pd
    from datetime import datetime, timezone

    results = [
        {"symbol": "EURUSD", "overall_pass": True, "evaluated_at_utc": "2026-03-19T12:00:00Z"},
    ]
    write_per_symbol_summaries(results, out_dir=tmp_path)

    df = pd.read_csv(tmp_path / "EURUSD_local_jforex_outcome_parity_summary.csv")
    assert "evaluated_at_utc" in df.columns, "Per-symbol CSV missing evaluated_at_utc"
    ts = df["evaluated_at_utc"].iloc[0]
    from datetime import datetime
    parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_reconcile_aggregate_csv_includes_evaluated_at_utc(tmp_path, monkeypatch):
    """Aggregate output CSV written by main() must include evaluated_at_utc for each symbol."""
    import pandas as pd
    import sys
    import duckdb
    import csv as csv_mod

    # Write minimal locked predictions and runtime events
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    reconcile_dir = tmp_path / "reconcile"
    reconcile_dir.mkdir()
    out_csv = tmp_path / "out.csv"

    # Minimal parquet: one selected prediction for EURUSD
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT '2025-07-07T12:00:00Z'::TIMESTAMPTZ AS close_ts, "
        "'uid_a' AS candidate_uid, 0.65 AS pred_prob, 3.5 AS target_gross_pips, "
        "1 AS target_gross_pos, 1 AS selected_exec, 0 AS event_ordinal) "
        f"TO '{lock_dir / 'eurusd_oco_locked_predictions.parquet'}' (FORMAT PARQUET)"
    )
    con.close()

    # Minimal runtime events — one predict_cycle with 1 selection + one order
    events_path = reconcile_dir / "EURUSD_jforex_runtime_events.csv"
    with open(events_path, "w", newline="") as f:
        writer = csv_mod.DictWriter(
            f,
            fieldnames=["event_ts_utc", "symbol", "category", "event_name", "pass", "detail"],
        )
        writer.writeheader()
        writer.writerow({
            "event_ts_utc": "2025-07-07T12:00:00Z", "symbol": "EURUSD",
            "category": "signal", "event_name": "predict_cycle", "pass": "true",
            "detail": "selected_count=1",
        })
        writer.writerow({
            "event_ts_utc": "2025-07-07T12:01:00Z", "symbol": "EURUSD",
            "category": "execution", "event_name": "order_submitted", "pass": "true",
            "detail": "OCO_EURUSD_T100_H6_TS20250707120000_RIDNA_CID001:BUY",
        })

    monkeypatch.setattr(
        sys, "argv",
        [
            "reconcile_jforex_outcomes.py",
            "--symbols", "EURUSD",
            "--lock-dir", str(lock_dir),
            "--reconcile-dir", str(reconcile_dir),
            "--out-csv", str(out_csv),
        ],
    )
    from scripts.reconcile_jforex_outcomes import main
    try:
        main()
    except SystemExit:
        pass  # exit code 0 or 1 is fine; we just need the CSV written

    df = pd.read_csv(out_csv)
    assert "evaluated_at_utc" in df.columns, "Aggregate CSV missing evaluated_at_utc"
    ts = df["evaluated_at_utc"].iloc[0]
    from datetime import datetime
    parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_load_runtime_events_prefers_real_over_local(tmp_path):
    """When both real-tester and local-surrogate event files exist, prefer the real one."""
    from scripts.reconcile_jforex_outcomes import load_runtime_events
    import csv

    # Real tester file: 5 predict_cycles
    real_path = tmp_path / "EURUSD_jforex_runtime_events.csv"
    with open(real_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["event_ts_utc", "symbol", "category", "event_name", "pass", "detail"],
        )
        writer.writeheader()
        for _ in range(5):
            writer.writerow({
                "event_ts_utc": "2025-07-07T12:00:00Z", "symbol": "EURUSD",
                "category": "signal", "event_name": "predict_cycle", "pass": "true",
                "detail": "selected_count=1",
            })

    # Local surrogate file: 99 predict_cycles (must NOT be selected)
    local_path = tmp_path / "EURUSD_local_jforex_runtime_events.csv"
    with open(local_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["event_ts_utc", "symbol", "category", "event_name", "pass", "detail"],
        )
        writer.writeheader()
        for _ in range(99):
            writer.writerow({
                "event_ts_utc": "2025-07-07T12:00:00Z", "symbol": "EURUSD",
                "category": "signal", "event_name": "predict_cycle", "pass": "true",
                "detail": "selected_count=1",
            })

    events = load_runtime_events(tmp_path, "EURUSD")
    assert events["predict_cycles"] == 5, (
        f"Expected 5 cycles from real tester file, got {events['predict_cycles']}. "
        "load_runtime_events() must prefer EURUSD_jforex_runtime_events.csv over "
        "EURUSD_local_jforex_runtime_events.csv."
    )


def test_main_reports_non_deployable_month_without_locked_predictions(tmp_path, monkeypatch):
    import json
    import pandas as pd
    import sys

    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    reconcile_dir = tmp_path / "reconcile"
    reconcile_dir.mkdir()
    out_csv = tmp_path / "out.csv"

    lock = {
        "symbol": "USDCAD",
        "artifacts": {
            "model_month": "2026-02",
            "predictions_path": "",
            "predictions_sha256": "",
            "live_deployable": False,
        },
        "state_universe": {"count": 0, "rows": []},
        "historical_backtest": {
            "target_month": "2026-02",
            "deployable": False,
            "non_deployable_reason": "no_gate_states",
        },
    }
    (lock_dir / "usdcad_oco_live_lock.json").write_text(json.dumps(lock), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "reconcile_jforex_outcomes.py",
            "--symbols",
            "USDCAD",
            "--lock-dir",
            str(lock_dir),
            "--reconcile-dir",
            str(reconcile_dir),
            "--out-csv",
            str(out_csv),
        ],
    )

    from scripts.reconcile_jforex_outcomes import main

    main()

    df = pd.read_csv(out_csv)
    row = df.iloc[0].to_dict()
    assert row["symbol"] == "USDCAD"
    assert str(row["historical_deployable"]).lower() == "false"
    assert row["non_deployable_reason"] == "no_gate_states"
    assert str(row["overall_pass"]).lower() == "false"

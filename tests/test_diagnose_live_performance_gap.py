#!/usr/bin/env python3
"""Tests for diagnose_live_performance_gap.py.

Uses a synthetic DuckDB with known data so we can assert specific
diagnostic findings without needing the live server.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest


def _make_synthetic_db(path: Path) -> None:
    """Create a minimal live_state.db with controlled trades and audit logs."""
    con = duckdb.connect(str(path))
    con.execute("""
        CREATE TABLE trades (
            internal_trade_id VARCHAR,
            broker_pos_id VARCHAR,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            side VARCHAR,
            entry_price DOUBLE,
            entry_ts TIMESTAMP WITH TIME ZONE,
            entry_bar_id INTEGER,
            horizon_bars INTEGER,
            touch_bar_id INTEGER,
            exit_price DOUBLE,
            exit_ts TIMESTAMP WITH TIME ZONE,
            pnl_pips DOUBLE,
            status VARCHAR,
            run_id VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE audit_logs (
            event_ts TIMESTAMP WITH TIME ZONE,
            close_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            pred_prob DOUBLE,
            threshold DOUBLE,
            features_json VARCHAR,
            model_month VARCHAR,
            run_id VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE account_risk_allocator_events (
            event_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            status VARCHAR,
            block_reason VARCHAR,
            reserved_loss_ccy DOUBLE,
            requested_volume_units DOUBLE,
            pred_prob DOUBLE,
            threshold_exec DOUBLE,
            risk_rank_score DOUBLE,
            reservation_id VARCHAR
        )
    """)
    now = datetime(2026, 3, 23, 14, 0, tzinfo=timezone.utc)
    # 10 CLOSED trades: 4 winners (+2.0 pips), 6 losers (-2.5 pips)
    for i in range(4):
        con.execute(
            "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'CLOSED','jforex_live')",
            [
                f"t{i}",
                f"bp{i}",
                "GBPUSD",
                "oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2",
                "BUY",
                1.3600,
                now,
                i,
                6,
                i + 3,
                1.3620,
                now,
                2.0,
            ],
        )
    for i in range(4, 10):
        con.execute(
            "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'CLOSED','jforex_live')",
            [
                f"t{i}",
                f"bp{i}",
                "GBPUSD",
                "oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2",
                "BUY",
                1.3600,
                now,
                i,
                6,
                None,
                1.3575,
                now,
                -2.5,
            ],
        )
    # Audit logs with pred_probs just above threshold
    for i in range(10):
        con.execute(
            "INSERT INTO audit_logs VALUES (?,?,'GBPUSD',?,?,?,'{}','2026-02','jforex_live')",
            [
                now,
                now,
                "oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2",
                0.596 + i * 0.001,  # pred_probs 0.596–0.605
                0.595,
            ],  # threshold
        )
    con.close()


def test_run_returns_report_with_all_sections(tmp_path: Path) -> None:
    db = tmp_path / "live_state.db"
    _make_synthetic_db(db)
    from scripts.diagnose_live_performance_gap import run

    report = run(db_path=db, run_id="jforex_live")
    assert "win_rate" in report
    assert "threshold_analysis" in report
    assert "magnitude_analysis" in report
    assert "candidate_audit" in report


def test_win_rate_computed_correctly(tmp_path: Path) -> None:
    db = tmp_path / "live_state.db"
    _make_synthetic_db(db)
    from scripts.diagnose_live_performance_gap import run

    report = run(db_path=db, run_id="jforex_live")
    gbp = next(r for r in report["win_rate"] if r["symbol"] == "GBPUSD")
    assert gbp["closed_trades"] == 10
    assert gbp["wins"] == 4
    assert abs(gbp["win_rate_pct"] - 40.0) < 0.1


def test_threshold_analysis_detects_static_fallback(tmp_path: Path) -> None:
    db = tmp_path / "live_state.db"
    _make_synthetic_db(db)
    from scripts.diagnose_live_performance_gap import run

    report = run(db_path=db, run_id="jforex_live")
    ta = report["threshold_analysis"]
    gbp = next(r for r in ta if r["symbol"] == "GBPUSD")
    # All audit logs used the same threshold → expect flag
    assert gbp["unique_thresholds"] == 1
    assert gbp["min_threshold"] == pytest.approx(0.595, abs=0.001)


def test_magnitude_analysis_checks_pips(tmp_path: Path) -> None:
    db = tmp_path / "live_state.db"
    _make_synthetic_db(db)
    from scripts.diagnose_live_performance_gap import run

    report = run(db_path=db, run_id="jforex_live")
    ma = report["magnitude_analysis"]
    gbp = next(r for r in ma if r["symbol"] == "GBPUSD")
    # avg_winner_pips and avg_loser_pips are variable (from_touch hold mode);
    # we just assert the values are present and have the correct sign.
    assert gbp["avg_winner_pips"] > 0
    assert gbp["avg_loser_pips"] < 0


def test_candidate_audit_identifies_locked_state(tmp_path: Path) -> None:
    db = tmp_path / "live_state.db"
    _make_synthetic_db(db)
    from scripts.diagnose_live_performance_gap import run

    report = run(db_path=db, run_id="jforex_live")
    ca = report["candidate_audit"]
    gbp = next(r for r in ca if r["symbol"] == "GBPUSD")
    assert gbp["distinct_candidate_uids"] == 1
    assert "ny_overlap" in gbp["candidate_uids"][0]


def test_rolling_threshold_integrity_section_detects_flat_warmup(tmp_path: Path) -> None:
    """The integrity section must flag a flat warmup distribution
    (unique_values == 1) as a regression of the historical replay bug."""
    from datetime import datetime, timedelta, timezone

    import duckdb

    db_path = tmp_path / "live_state.db"
    con = duckdb.connect(str(db_path))
    con.execute("""
        CREATE TABLE audit_logs (
            event_ts TIMESTAMP WITH TIME ZONE,
            close_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            pred_prob DOUBLE,
            threshold DOUBLE,
            features_json VARCHAR,
            model_month VARCHAR,
            run_id VARCHAR
        )
    """)
    now = datetime.now(tz=timezone.utc)
    uid = "oco|USDJPY|1000|h6|oco_first_touch_clean__all__k2"
    for i in range(300):
        con.execute(
            "INSERT INTO audit_logs VALUES (?, ?, 'USDJPY', ?, 0.6988, 0.5, '{}', '2026-03', 'warmup')",
            [now, now - timedelta(hours=i), uid],
        )
    for i in range(60):
        con.execute(
            "INSERT INTO audit_logs VALUES (?, ?, 'USDJPY', ?, ?, 0.5, '{}', '2026-03', 'threshold_seed')",
            [now, now - timedelta(hours=i + 1), uid, 0.50 + 0.005 * i],
        )
    con.close()

    from scripts.diagnose_live_performance_gap import _rolling_threshold_integrity_section

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = _rolling_threshold_integrity_section(con)
    finally:
        con.close()

    warmup_row = next(r for r in rows if r["symbol"] == "USDJPY" and r["run_id"] == "warmup")
    assert warmup_row["unique_values"] == 1
    assert warmup_row["flag"] is True

    seed_row = next(
        r for r in rows if r["symbol"] == "USDJPY" and r["run_id"] == "threshold_seed"
    )
    assert seed_row["unique_values"] > 10
    assert seed_row["flag"] is False


def test_run_and_format_report_include_integrity_section(tmp_path: Path) -> None:
    db = tmp_path / "live_state.db"
    _make_synthetic_db(db)

    con = duckdb.connect(str(db))
    now = datetime(2026, 3, 23, 14, 0, tzinfo=timezone.utc)
    uid = "oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2"
    for _i in range(40):
        con.execute(
            "INSERT INTO audit_logs VALUES (?, ?, 'GBPUSD', ?, 0.6123, 0.595, '{}', '2026-02', 'warmup')",
            [now, now, uid],
        )
    con.close()

    from scripts.diagnose_live_performance_gap import _format_report, run

    report = run(db_path=db, run_id="jforex_live")
    assert "rolling_threshold_integrity" in report
    warmup_row = next(
        r for r in report["rolling_threshold_integrity"] if r["symbol"] == "GBPUSD" and r["run_id"] == "warmup"
    )
    assert warmup_row["flag"] is True

    rendered = _format_report(report)
    assert "## 5. Rolling Threshold Integrity" in rendered
    assert "low-cardinality audit population" in rendered
    assert "For `run_id == 'warmup'`" in rendered
    assert f"| GBPUSD | {uid} | warmup | 40 | 1 |" in rendered

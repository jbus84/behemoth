from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb

from scripts.summarize_runtime_db_run import run


def _create_db(path: Path) -> None:
    now = datetime(2025, 7, 25, 10, 30, tzinfo=timezone.utc)
    con = duckdb.connect(str(path))
    con.execute(
        """
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
            status VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE audit_logs (
            event_ts TIMESTAMP WITH TIME ZONE,
            close_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            pred_prob DOUBLE,
            threshold DOUBLE,
            features_json VARCHAR,
            model_month VARCHAR
        )
        """
    )

    con.execute(
        """
        INSERT INTO trades VALUES
        ('t1','bp1','EURUSD','oco|EURUSD|100|h5|a','BUY',1.10,?,1,5,NULL,1.11,?,10.0,'CLOSED'),
        ('t2','bp2','EURUSD','oco|EURUSD|100|h5|b','SELL',1.10,?,2,5,NULL,NULL,NULL,NULL,'OPEN')
        """,
        [now, now, now],
    )
    con.execute(
        """
        INSERT INTO audit_logs VALUES
        (?,?,'EURUSD','oco|EURUSD|100|h5|a',0.8,0.6,'{}','2025-07'),
        (?,?,'EURUSD','oco|EURUSD|100|h5|b',0.7,0.6,'{}','2025-07')
        """,
        [now, now, now, now],
    )
    con.close()


def test_summarize_runtime_db_run_outputs_counts(tmp_path: Path) -> None:
    db = tmp_path / "runtime.db"
    _create_db(db)

    out = run(
        runtime_db_path=db,
        symbol="EURUSD",
        start_ts="2025-07-25T00:00:00Z",
        end_ts="2025-07-26T00:00:00Z",
        out_csv=tmp_path / "summary.csv",
        report_out=tmp_path / "summary.md",
    )

    row = out.iloc[0]
    assert bool(row["runtime_db_exists"]) is True
    assert int(row["trades_symbol_rows"]) == 2
    assert int(row["trades_window_rows"]) == 2
    assert int(row["audit_symbol_rows"]) == 2
    assert int(row["audit_window_rows"]) == 2
    assert str(row["audit_window_source"]) == "close_ts"
    assert int(row["trades_window_closed_rows"]) == 1
    assert (tmp_path / "summary.csv").exists()
    assert (tmp_path / "summary.md").exists()


def test_summarize_runtime_db_run_missing_db(tmp_path: Path) -> None:
    out = run(
        runtime_db_path=tmp_path / "missing.db",
        symbol="EURUSD",
        start_ts="2025-07-25T00:00:00Z",
        end_ts="2025-07-26T00:00:00Z",
        out_csv=tmp_path / "summary.csv",
        report_out=tmp_path / "summary.md",
    )
    row = out.iloc[0]
    assert bool(row["runtime_db_exists"]) is False
    assert int(row["trades_symbol_rows"]) == 0
    assert int(row["audit_symbol_rows"]) == 0


def test_summarize_prefers_close_ts_for_windowing(tmp_path: Path) -> None:
    db = tmp_path / "runtime.db"
    _create_db(db)
    con = duckdb.connect(str(db))
    try:
        con.execute(
            "UPDATE audit_logs SET event_ts = TIMESTAMPTZ '2026-03-09T12:00:00+00:00'"
        )
    finally:
        con.close()

    out = run(
        runtime_db_path=db,
        symbol="EURUSD",
        start_ts="2025-07-25T00:00:00Z",
        end_ts="2025-07-26T00:00:00Z",
        out_csv=tmp_path / "summary.csv",
        report_out=tmp_path / "summary.md",
    )
    row = out.iloc[0]
    assert int(row["audit_event_window_rows"]) == 0
    assert int(row["audit_close_window_rows"]) == 2
    assert int(row["audit_window_rows"]) == 2
    assert str(row["audit_window_source"]) == "close_ts"


def test_summarize_legacy_audit_schema_without_close_ts(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    now = datetime(2025, 7, 25, 10, 30, tzinfo=timezone.utc)
    con = duckdb.connect(str(db))
    try:
        con.execute(
            """
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
                status VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE audit_logs (
                event_ts TIMESTAMP WITH TIME ZONE,
                symbol VARCHAR,
                candidate_uid VARCHAR,
                pred_prob DOUBLE,
                threshold DOUBLE,
                features_json VARCHAR,
                model_month VARCHAR
            )
            """
        )
        con.execute(
            """
            INSERT INTO trades VALUES
            ('t1','bp1','EURUSD','oco|EURUSD|100|h5|a','BUY',1.10,?,1,5,NULL,1.11,?,10.0,'CLOSED')
            """,
            [now, now],
        )
        con.execute(
            """
            INSERT INTO audit_logs VALUES
            (?,'EURUSD','oco|EURUSD|100|h5|a',0.8,0.6,'{}','2025-07')
            """,
            [now],
        )
    finally:
        con.close()

    out = run(
        runtime_db_path=db,
        symbol="EURUSD",
        start_ts="2025-07-25T00:00:00Z",
        end_ts="2025-07-26T00:00:00Z",
        out_csv=tmp_path / "summary.csv",
        report_out=tmp_path / "summary.md",
    )
    row = out.iloc[0]
    assert int(row["audit_symbol_rows"]) == 1
    assert int(row["audit_window_rows"]) == 1
    assert str(row["audit_window_source"]) == "event_ts"

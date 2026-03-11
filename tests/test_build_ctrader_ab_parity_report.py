from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from scripts.build_ctrader_ab_parity_report import run


def _create_runtime_db(path: Path) -> None:
    t0 = datetime(2025, 7, 7, 10, 30, tzinfo=timezone.utc)
    t1 = datetime(2025, 7, 7, 10, 31, tzinfo=timezone.utc)
    t2 = datetime(2025, 7, 7, 10, 30, 1, tzinfo=timezone.utc)

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
        CREATE TABLE raw_ticks (
            tick_ts TIMESTAMP WITH TIME ZONE,
            ingest_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            bid DOUBLE,
            ask DOUBLE,
            spread DOUBLE,
            tick_volume DOUBLE,
            source VARCHAR
        )
        """
    )

    con.execute(
        """
        INSERT INTO trades VALUES
        ('t1','bp1','EURUSD','oco|EURUSD|100|h5|a','BUY',1.1,?,1,5,NULL,1.1005,?,5.0,'CLOSED')
        """,
        [t0, t1],
    )
    con.execute(
        """
        INSERT INTO audit_logs VALUES
        (?,?,'EURUSD','oco|EURUSD|100|h5|a',0.82,0.60,'{}','2025-07'),
        (?,?,'EURUSD','oco|EURUSD|100|h5|b',0.79,0.60,'{}','2025-07')
        """,
        [t0, t0, t1, t1],
    )
    con.execute(
        """
        INSERT INTO raw_ticks VALUES
        (?,?,'EURUSD',1.1000,1.1002,0.0002,1.0,'historical_backtest'),
        (?,?,'EURUSD',1.1001,1.1003,0.0002,1.0,'historical_backtest'),
        (?,?,'EURUSD',1.1002,1.1004,0.0002,1.0,'historical_backtest')
        """,
        [t0, t0, t2, t2, t1, t1],
    )
    con.close()


def _create_predictions(path: Path) -> None:
    rows = [
        {
            "close_ts": "2025-07-07T10:30:00Z",
            "candidate_uid": "oco|EURUSD|100|h5|a",
            "pred_prob": 0.82,
            "threshold_exec": 0.60,
            "selected_exec": 1,
            "threshold_source": "rolling_days:schedule",
            "test_month": "2025-07",
        },
        {
            "close_ts": "2025-07-07T10:31:00Z",
            "candidate_uid": "oco|EURUSD|100|h5|b",
            "pred_prob": 0.79,
            "threshold_exec": 0.60,
            "selected_exec": 1,
            "threshold_source": "rolling_days:schedule",
            "test_month": "2025-07",
        },
    ]
    pd.DataFrame(rows).to_parquet(path, index=False)


def _create_hist_ticks(tick_root: Path) -> None:
    out = pd.DataFrame(
        [
            {
                "timestamp": "2025-07-07T10:30:00Z",
                "bid": 1.1000,
                "ask": 1.1002,
                "mid": 1.1001,
                "spread": 0.0002,
                "log_return": 0.0,
            },
            {
                "timestamp": "2025-07-07T10:30:01Z",
                "bid": 1.1001,
                "ask": 1.1003,
                "mid": 1.1002,
                "spread": 0.0002,
                "log_return": 0.0,
            },
            {
                "timestamp": "2025-07-07T10:31:00Z",
                "bid": 1.1002,
                "ask": 1.1004,
                "mid": 1.1003,
                "spread": 0.0002,
                "log_return": 0.0,
            },
        ]
    )
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out_dir = tick_root / "EURUSD"
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_dir / "EURUSD_202507_ticks.parquet", index=False)


def test_build_ctrader_ab_parity_report_green_for_identical_runs(tmp_path: Path) -> None:
    db_a = tmp_path / "run_a.db"
    db_b = tmp_path / "run_b.db"
    pred = tmp_path / "pred.parquet"
    tick_root = tmp_path / "tick"

    _create_runtime_db(db_a)
    _create_runtime_db(db_b)
    _create_predictions(pred)
    _create_hist_ticks(tick_root)

    summary_path = tmp_path / "eurusd_ab_summary.csv"
    checks_path = tmp_path / "eurusd_ab_checks.csv"
    report_path = tmp_path / "eurusd_ab_report.md"

    summary, checks = run(
        symbol="EURUSD",
        runtime_db_a=db_a,
        runtime_db_b=db_b,
        predictions_parquet=pred,
        tick_root=tick_root,
        history_dir=None,
        start_ts="2025-07-07T10:29:00Z",
        end_ts="2025-07-07T10:32:00Z",
        strict_window=True,
        timestamp_tolerance_sec=2.0,
        out_summary_csv=summary_path,
        out_checks_csv=checks_path,
        report_out=report_path,
    )

    assert summary_path.exists()
    assert checks_path.exists()
    assert report_path.exists()
    assert summary.iloc[0]["parity_verdict"] == "green"

    hc = checks[checks["check_id"].astype(str) == "AB_HC_FAILURES_BOTH_EQ_0"].iloc[0]
    assert hc["status"] == "pass"

    base_name = summary_path.stem
    assert (summary_path.parent / f"{base_name}_A_ctrader_vs_research_checks.csv").exists()
    assert (summary_path.parent / f"{base_name}_B_ctrader_vs_research_checks.csv").exists()

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from scripts.build_ftmo_allocator_monitoring_report import METRIC_SPECS, run


def _create_runtime_db(path: Path) -> None:
    now = datetime.now(timezone.utc)
    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE ftmo_allocator_events (
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
        """
    )
    con.execute(
        """
        CREATE TABLE ftmo_risk_reservations (
            reservation_id VARCHAR,
            created_ts TIMESTAMP WITH TIME ZONE,
            updated_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            broker_pos_id VARCHAR,
            status VARCHAR,
            reserved_loss_ccy DOUBLE,
            barrier_pips DOUBLE,
            cap_pips DOUBLE,
            cost_est_pips DOUBLE,
            volume_units DOUBLE,
            side VARCHAR,
            source VARCHAR
        )
        """
    )
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

    rows_events = [
        [
            now - timedelta(hours=1),
            "EURUSD",
            "cand_1",
            "ADMITTED",
            None,
            50.0,
            10000.0,
            0.9,
            0.6,
            1.0,
            "r1",
        ],
        [
            now - timedelta(hours=2),
            "EURUSD",
            "cand_2",
            "BLOCKED",
            "FTMO_RESERVED_BUDGET_EXCEEDED",
            None,
            10000.0,
            0.8,
            0.6,
            0.9,
            None,
        ],
        [
            now - timedelta(hours=3),
            "EURUSD",
            "cand_3",
            "BLOCKED",
            "FTMO_RESERVED_BUDGET_EXCEEDED",
            None,
            10000.0,
            0.81,
            0.6,
            0.8,
            None,
        ],
        [
            now - timedelta(hours=4),
            "EURUSD",
            "cand_4",
            "BLOCKED",
            "FTMO_PIP_VALUE_UNAVAILABLE",
            None,
            10000.0,
            0.82,
            0.6,
            0.7,
            None,
        ],
    ]
    con.executemany(
        "INSERT INTO ftmo_allocator_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows_events,
    )

    rows_res = [
        [
            "r1",
            now - timedelta(hours=4),
            now - timedelta(hours=1),
            "EURUSD",
            "cand_1",
            "bp1",
            "OPEN",
            50.0,
            3.0,
            1.2,
            0.8,
            10000.0,
            "BUY",
            "predict_allocator",
        ],
        [
            "r2",
            now - timedelta(hours=12),
            now - timedelta(hours=12),
            "EURUSD",
            "cand_2",
            None,
            "PENDING",
            40.0,
            3.0,
            1.2,
            0.8,
            10000.0,
            "BUY",
            "predict_allocator",
        ],
        [
            "r3",
            now - timedelta(hours=2),
            now - timedelta(hours=2),
            "EURUSD",
            "cand_3",
            "",
            "OPEN",
            20.0,
            3.0,
            1.2,
            0.8,
            10000.0,
            "BUY",
            "predict_allocator",
        ],
    ]
    con.executemany(
        "INSERT INTO ftmo_risk_reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows_res,
    )
    con.execute(
        """
        INSERT INTO trades VALUES
        ('t1', 'bp1', 'EURUSD', 'cand_1', 'BUY', 1.1, ?, 1, 5, NULL, NULL, NULL, NULL, 'OPEN')
        """,
        [now - timedelta(hours=1)],
    )
    con.close()


def test_build_ftmo_allocator_monitoring_outputs_metrics_and_alerts(tmp_path: Path) -> None:
    db = tmp_path / "runtime.db"
    _create_runtime_db(db)

    metrics, alerts = run(
        symbols=["EURUSD", "USDCHF"],
        runtime_db_path=db,
        lookback_days=7,
        stale_pending_hours=6.0,
        stale_open_hours=72.0,
        out_metrics_csv=tmp_path / "metrics.csv",
        out_alerts_csv=tmp_path / "alerts.csv",
        report_out=tmp_path / "report.md",
    )

    assert not metrics.empty
    eur_block = metrics[
        (metrics["symbol"].astype(str) == "EURUSD")
        & (metrics["metric_id"].astype(str) == "FTMO_ALLOC_BLOCK_RATE")
    ]
    assert not eur_block.empty
    assert float(eur_block.iloc[0]["metric_value"]) == 0.75

    eur_alert = alerts[
        (alerts["symbol"].astype(str) == "EURUSD")
        & (alerts["metric_id"].astype(str) == "FTMO_ALLOC_BLOCK_RATE")
    ]
    assert not eur_alert.empty
    assert eur_alert.iloc[0]["band"] == "red"

    assert (tmp_path / "metrics.csv").exists()
    assert (tmp_path / "alerts.csv").exists()
    assert (tmp_path / "report.md").exists()


def test_build_ftmo_allocator_monitoring_handles_missing_db(tmp_path: Path) -> None:
    metrics, alerts = run(
        symbols=["EURUSD"],
        runtime_db_path=tmp_path / "missing_runtime.db",
        lookback_days=7,
        stale_pending_hours=6.0,
        stale_open_hours=72.0,
        out_metrics_csv=tmp_path / "metrics.csv",
        out_alerts_csv=tmp_path / "alerts.csv",
        report_out=tmp_path / "report.md",
    )
    assert not metrics.empty
    assert set(metrics["metric_id"].astype(str)).issuperset(
        {x["metric_id"] for x in METRIC_SPECS}
    )
    assert len(alerts) == len(METRIC_SPECS)
    assert (alerts["band"].astype(str) == "green").all()

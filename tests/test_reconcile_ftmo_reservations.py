from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from scripts.reconcile_ftmo_reservations import run


def _create_db(path: Path, *, with_mismatch: bool) -> None:
    now = datetime.now(timezone.utc)
    con = duckdb.connect(str(path))
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

    if with_mismatch:
        con.executemany(
            "INSERT INTO ftmo_risk_reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                [
                    "r1",
                    now - timedelta(hours=12),
                    now - timedelta(hours=12),
                    "EURUSD",
                    "cand_1",
                    "",
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
                    now - timedelta(hours=20),
                    now - timedelta(hours=20),
                    "EURUSD",
                    "cand_2",
                    None,
                    "PENDING",
                    25.0,
                    3.0,
                    1.2,
                    0.8,
                    10000.0,
                    "BUY",
                    "predict_allocator",
                ],
            ],
        )
        con.executemany(
            "INSERT INTO ftmo_allocator_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
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
                    "",
                ],
                [
                    now - timedelta(hours=2),
                    "EURUSD",
                    "cand_2",
                    "ADMITTED",
                    None,
                    30.0,
                    10000.0,
                    0.85,
                    0.6,
                    0.9,
                    "unknown_res",
                ],
            ],
        )
    else:
        con.executemany(
            "INSERT INTO ftmo_risk_reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                [
                    "r1",
                    now - timedelta(hours=1),
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
                ]
            ],
        )
        con.execute(
            "INSERT INTO ftmo_allocator_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        )
        con.execute(
            """
            INSERT INTO trades VALUES
            ('t1', 'bp1', 'EURUSD', 'cand_1', 'BUY', 1.1, ?, 1, 5, NULL, NULL, NULL, NULL, 'OPEN')
            """,
            [now - timedelta(hours=1)],
        )
    con.close()


def test_reconcile_ftmo_reservations_detects_mismatches(tmp_path: Path) -> None:
    db = tmp_path / "runtime_mismatch.db"
    _create_db(db, with_mismatch=True)

    out = run(
        symbols=["EURUSD"],
        runtime_db_path=db,
        event_lookback_days=30,
        stale_pending_hours=6.0,
        stale_open_hours=72.0,
        out_csv=tmp_path / "recon.csv",
        report_out=tmp_path / "report.md",
    )
    eur = out[out["symbol"].astype(str) == "EURUSD"].iloc[0]
    assert bool(eur["reconciliation_pass"]) is False
    assert int(eur["stale_pending_count"]) >= 1
    assert int(eur["open_without_broker_pos_count"]) >= 1
    assert int(eur["admitted_missing_reservation_id_count"]) >= 1
    assert int(eur["admitted_unknown_reservation_id_count"]) >= 1
    assert (tmp_path / "recon.csv").exists()
    assert (tmp_path / "report.md").exists()


def test_reconcile_ftmo_reservations_passes_when_aligned(tmp_path: Path) -> None:
    db = tmp_path / "runtime_ok.db"
    _create_db(db, with_mismatch=False)
    out = run(
        symbols=["EURUSD"],
        runtime_db_path=db,
        event_lookback_days=30,
        stale_pending_hours=6.0,
        stale_open_hours=72.0,
        out_csv=tmp_path / "recon.csv",
        report_out=tmp_path / "report.md",
    )
    eur = out[out["symbol"].astype(str) == "EURUSD"].iloc[0]
    assert bool(eur["reconciliation_pass"]) is True
    all_row = out[out["symbol"].astype(str) == "ALL"].iloc[0]
    assert bool(all_row["reconciliation_pass"]) is True

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.build_ctrader_debug_bundle import build_bundle


def _write_runtime_db(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
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
                source VARCHAR,
                client_tick_seq BIGINT,
                run_id VARCHAR
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
                model_month VARCHAR,
                run_id VARCHAR
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
                status VARCHAR,
                run_id VARCHAR
            )
            """
        )
        con.execute(
            """
            INSERT INTO raw_ticks VALUES
            ('2025-07-07T00:00:00Z', '2025-07-07T00:00:00Z', 'EURUSD', 1.1, 1.1001, 0.0001, 1.0, 'historical_backtest', 1, 'eurusd_debug_case')
            """
        )
        con.execute(
            """
            INSERT INTO audit_logs VALUES
            ('2025-07-07T00:00:10Z', '2025-07-07T00:00:00Z', 'EURUSD', 'oco|EURUSD|100|h6|state_a', 0.9, 0.7, '{}', '2025-07', 'eurusd_debug_case')
            """
        )
        con.execute(
            """
            INSERT INTO trades VALUES
            ('internal-1', '42', 'EURUSD', 'oco|EURUSD|100|h6|state_a', 'Buy', 1.1002, '2025-07-07T00:00:12Z', 10, 6, NULL, 1.1008, '2025-07-07T00:00:30Z', 6.0, 'CLOSED', 'eurusd_debug_case')
            """
        )
    finally:
        con.close()


def test_build_bundle_writes_joined_outputs(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)

    runtime_db = bundle_dir / "runtime.db"
    _write_runtime_db(runtime_db)

    (bundle_dir / "http_trace.ndjson").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts_utc": "2025-07-07T00:00:00Z",
                        "endpoint": "/ticks",
                        "phase": "request",
                        "run_id": "eurusd_debug_case",
                        "symbol": "EURUSD",
                        "status_code": None,
                        "request": {"client_tick_seq": 1, "symbol": "EURUSD"},
                        "response": None,
                        "extra": {},
                    }
                ),
                json.dumps(
                    {
                        "ts_utc": "2025-07-07T00:00:10Z",
                        "endpoint": "/predict",
                        "phase": "response",
                        "run_id": "eurusd_debug_case",
                        "symbol": "EURUSD",
                        "status_code": 200,
                        "request": {"symbol": "EURUSD"},
                        "response": [{"candidate_uid": "oco|EURUSD|100|h6|state_a"}],
                        "extra": {"completed_bar_ticks": [100]},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (bundle_dir / "cbot.log").write_text(
        "07/07/2025 00:00:10.000 | Info | [PREDICT] completed_bar_ticks=100\n",
        encoding="utf-8",
    )
    (bundle_dir / "events.json").write_text(
        json.dumps(
            [
                {
                    "event": "Create Position",
                    "positionId": 42,
                    "type": "Buy",
                    "time": 1751846412000,
                    "entryPrice": 1.1002,
                },
                {
                    "event": "Position closed",
                    "positionId": 42,
                    "type": "Buy",
                    "time": 1751846430000,
                    "closePrice": 1.1008,
                    "pips": 6.0,
                },
            ]
        ),
        encoding="utf-8",
    )

    expected_dir = tmp_path / "data" / "analysis" / "tick_opportunity_mining" / "stop_limit_tickfill_fullcap"
    expected_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "close_ts": "2025-07-07T00:00:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|state_a",
                "side": "BUY",
                "bar_ticks": 100,
                "horizon": 6,
                "barrier_pips": 3.0,
                "touch_open_ts": "2025-07-07T00:00:12Z",
                "touch_close_ts": "2025-07-07T00:00:30Z",
            }
        ]
    ).to_csv(expected_dir / "EURUSD_stop_limit_tickfill_detail.csv", index=False)

    session_path = bundle_dir / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "run_id": "eurusd_debug_case",
                "symbol": "EURUSD",
                "start_ts": "2025-07-07T00:00:00Z",
                "end_ts": "2025-07-09T00:00:00Z",
                "bundle_dir": str(bundle_dir),
                "bundle_runtime_db": str(runtime_db),
                "bundle_http_trace": str(bundle_dir / "http_trace.ndjson"),
                "bundle_cbot_log": str(bundle_dir / "cbot.log"),
                "bundle_ctrader_events": str(bundle_dir / "events.json"),
                "offline_stop_limit_detail_csv": str(expected_dir / "EURUSD_stop_limit_tickfill_detail.csv"),
                "history_dir": str(tmp_path / "missing_history_dir"),
            }
        ),
        encoding="utf-8",
    )

    out = build_bundle(session_path=session_path, bundle_dir=bundle_dir)
    assert Path(out["joined_timeline_csv"]).exists()
    assert Path(out["joined_timeline_md"]).exists()
    assert Path(out["debug_summary_csv"]).exists()
    assert Path(out["offline_compare_csv"]).exists()
    assert Path(out["offline_compare_exact_csv"]).exists()
    assert Path(out["offline_compare_tolerant_csv"]).exists()

    timeline = pd.read_csv(out["joined_timeline_csv"])
    assert {"http_trace", "runtime_db", "ctrader_events", "cbot_log"}.issubset(set(timeline["source"]))

    compare = pd.read_csv(out["offline_compare_csv"])
    assert compare.loc[0, "runtime_predicted"] in (True, 1)
    assert compare.loc[0, "runtime_executed"] in (True, 1)


def test_build_bundle_writes_tolerant_compare_when_runtime_timestamps_drift(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)

    runtime_db = bundle_dir / "runtime.db"
    _write_runtime_db(runtime_db)

    con = duckdb.connect(str(runtime_db))
    try:
        con.execute(
            """
            DELETE FROM audit_logs;
            DELETE FROM trades;
            INSERT INTO audit_logs VALUES
            ('2025-07-07T00:00:16Z', '2025-07-07T00:00:16Z', 'EURUSD', 'oco|EURUSD|100|h6|state_a', 0.9, 0.7, '{}', '2025-07', 'eurusd_debug_case')
            """
        )
        con.execute(
            """
            INSERT INTO trades VALUES
            ('internal-1', '42', 'EURUSD', 'oco|EURUSD|100|h6|state_a', 'Buy', 1.1002, '2025-07-07T00:00:18Z', 10, 6, NULL, 1.1008, '2025-07-07T00:00:30Z', 6.0, 'CLOSED', 'eurusd_debug_case')
            """
        )
    finally:
        con.close()

    expected_dir = tmp_path / "data" / "analysis" / "tick_opportunity_mining" / "stop_limit_tickfill_fullcap"
    expected_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "close_ts": "2025-07-07T00:00:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|state_a",
                "side": "BUY",
                "bar_ticks": 100,
                "horizon": 6,
                "barrier_pips": 3.0,
                "touch_open_ts": "2025-07-07T00:00:12Z",
                "touch_close_ts": "2025-07-07T00:00:30Z",
            }
        ]
    ).to_csv(expected_dir / "EURUSD_stop_limit_tickfill_detail.csv", index=False)

    session_path = bundle_dir / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "run_id": "eurusd_debug_case",
                "symbol": "EURUSD",
                "start_ts": "2025-07-07T00:00:00Z",
                "end_ts": "2025-07-09T00:00:00Z",
                "bundle_dir": str(bundle_dir),
                "bundle_runtime_db": str(runtime_db),
                "offline_stop_limit_detail_csv": str(expected_dir / "EURUSD_stop_limit_tickfill_detail.csv"),
                "history_dir": str(tmp_path / "missing_history_dir"),
            }
        ),
        encoding="utf-8",
    )

    out = build_bundle(session_path=session_path, bundle_dir=bundle_dir)
    exact_compare = pd.read_csv(out["offline_compare_exact_csv"])
    tolerant_compare = pd.read_csv(out["offline_compare_tolerant_csv"])

    assert exact_compare.loc[0, "runtime_predicted"] in (False, 0)
    assert exact_compare.loc[0, "runtime_executed"] in (False, 0)
    assert tolerant_compare.loc[0, "runtime_predicted"] in (True, 1)
    assert tolerant_compare.loc[0, "runtime_executed"] in (True, 1)

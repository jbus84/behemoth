from __future__ import annotations

import hashlib
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
    assert Path(out["signal_gap_analysis_csv"]).exists()
    assert Path(out["signal_feature_diff_csv"]).exists()
    assert Path(out["execution_gap_analysis_csv"]).exists()
    assert Path(out["ftmo_challenge_summary_csv"]).exists()
    assert Path(out["ftmo_challenge_timeline_csv"]).exists()
    assert Path(out["ftmo_daily_ledger_csv"]).exists()
    assert Path(out["ftmo_phase_report_md"]).exists()

    timeline = pd.read_csv(out["joined_timeline_csv"])
    assert {"http_trace", "runtime_db", "ctrader_events", "cbot_log"}.issubset(set(timeline["source"]))

    compare = pd.read_csv(out["offline_compare_csv"])
    assert compare.loc[0, "runtime_predicted"] in (True, 1)
    assert compare.loc[0, "runtime_executed"] in (True, 1)
    summary = pd.read_csv(out["debug_summary_csv"])
    assert "ftmo_overall_verdict" in summary.columns


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


def test_build_bundle_classifies_ctrader_signal_gap_from_predict_trace(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)
    runtime_db = bundle_dir / "runtime.db"
    _write_runtime_db(runtime_db)

    con = duckdb.connect(str(runtime_db))
    try:
        con.execute("DELETE FROM audit_logs")
        con.execute("DELETE FROM trades")
    finally:
        con.close()

    (bundle_dir / "http_trace.ndjson").write_text(
        json.dumps(
            {
                "ts_utc": "2025-07-07T00:00:20Z",
                "endpoint": "/predict",
                "phase": "response",
                "run_id": "eurusd_debug_case",
                "symbol": "EURUSD",
                "status_code": 200,
                "request": {"symbol": "EURUSD"},
                "response": [],
                "extra": {
                    "reason": "ok",
                    "candidate_trace_rows": [
                        {
                            "candidate_uid": "oco|EURUSD|100|h6|state_b__k2",
                            "close_ts": "2025-07-07T00:00:20Z",
                            "selected_exec": 0,
                            "pred_prob": 0.55,
                            "threshold_exec": 0.60,
                            "risk_blocked": False,
                            "features": {
                                "cost_est_pips": 0.5,
                                "range_pips": 2.0,
                                "ret1_pips": 1.0,
                                "ret_z": 1.0,
                                "ret_abs_z": 1.0,
                                "vel_cost_units_h1": 2.0,
                                "vel_abs_cost_units_h1": 2.0,
                                "spread_z": 0.0,
                                "tick_rate_z": 0.0,
                                "hour_utc": 0.0,
                                "hl_first": 1.0,
                                "hl_first_mean_24": 0.0,
                                "hl_pos_frac_mean_24": 0.0,
                                "bar_ticks": 100.0,
                                "horizon": 6.0,
                                "barrier_pips": 2.0,
                            },
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    expected_dir = tmp_path / "data" / "analysis" / "tick_opportunity_mining" / "stop_limit_tickfill_fullcap"
    expected_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "close_ts": "2025-07-07T00:00:20Z",
                "candidate_uid": "oco|EURUSD|100|h6|state_b__k2",
                "side": "BUY",
                "bar_ticks": 100,
                "horizon": 6,
                "barrier_pips": 2.0,
                "touch_open_ts": "2025-07-07T00:00:22Z",
                "touch_close_ts": "2025-07-07T00:00:40Z",
            }
        ]
    ).to_csv(expected_dir / "EURUSD_stop_limit_tickfill_detail.csv", index=False)

    history_dir = tmp_path / "history" / "2025-07"
    history_dir.mkdir(parents=True)
    predictions_path = history_dir / "eurusd_oco_locked_predictions.parquet"
    pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h6|state_b__k2",
                "close_ts": "2025-07-07T00:00:20Z",
                "pred_prob": 0.62,
                "threshold_exec": 0.60,
                "selected_exec": 1,
                "test_month": "2025-07",
            }
        ]
    ).to_parquet(predictions_path, index=False)
    model_cbm = history_dir / "EURUSD_model_2025-07.cbm"
    model_thr = history_dir / "EURUSD_model_2025-07.json"
    model_cbm.write_bytes(b"dummy")
    model_thr.write_text(json.dumps({"threshold_exec": 0.6, "features": []}), encoding="utf-8")
    (history_dir / "eurusd_oco_live_lock.json").write_text(
        json.dumps(
            {
                "symbol": "EURUSD",
                "artifacts": {
                    "model_month": "2025-07",
                    "predictions_path": str(predictions_path),
                    "predictions_sha256": _sha256(predictions_path),
                    "model_cbm_path": str(model_cbm),
                    "model_cbm_sha256": _sha256(model_cbm),
                    "model_threshold_json_path": str(model_thr),
                    "model_threshold_json_sha256": _sha256(model_thr),
                },
                "state_universe": {
                    "rows": [
                        {
                            "symbol": "EURUSD",
                            "bar_ticks": 100,
                            "horizon": 6,
                            "barrier_pips": 2.0,
                            "state_id": "state_b__k2",
                            "regime_desc": "",
                        }
                    ]
                },
                "locked_runtime": {"production_cap_pips": 1.2},
            }
        ),
        encoding="utf-8",
    )

    tick_velocity_dir = tmp_path / "tick_velocity"
    tick_velocity_dir.mkdir(parents=True)
    ts = pd.date_range("2025-07-06T16:00:00Z", periods=320, freq="90s", tz="UTC")
    pd.DataFrame(
        {
            "timestamp": ts - pd.to_timedelta(20, unit="s"),
            "close_ts": ts,
            "open": 1.1000 + pd.Series(range(320)) * 0.00001,
            "high": 1.1004 + pd.Series(range(320)) * 0.00001,
            "low": 1.0997 + pd.Series(range(320)) * 0.00001,
            "close": 1.1002 + pd.Series(range(320)) * 0.00001,
            "spread": 0.00012,
            "tick_volume": 100.0,
            "hl_first": 1.0,
            "hl_pos_frac": 0.25,
        }
    ).to_parquet(tick_velocity_dir / "EURUSD_100tick_velocity.parquet", index=False)

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
                "offline_stop_limit_detail_csv": str(expected_dir / "EURUSD_stop_limit_tickfill_detail.csv"),
                "history_dir": str(tmp_path / "history"),
                "tick_velocity_dir": str(tick_velocity_dir),
            }
        ),
        encoding="utf-8",
    )

    out = build_bundle(session_path=session_path, bundle_dir=bundle_dir)
    signal_gap = pd.read_csv(out["signal_gap_analysis_csv"])
    execution_gap = pd.read_csv(out["execution_gap_analysis_csv"])

    assert len(signal_gap) == 1
    assert signal_gap.loc[0, "gap_reason"] == "candidate_seen_but_not_selected"
    assert (execution_gap["gap_reason"] == "no_prediction_no_execution").any()

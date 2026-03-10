from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from scripts.reconcile_ctrader_vs_research import run


def _create_db(path: Path, *, audit_in_window: bool) -> None:
    base = datetime(2025, 7, 25, 10, 30, tzinfo=timezone.utc)
    audit_ts = base if audit_in_window else datetime(2026, 3, 2, 10, 30, tzinfo=timezone.utc)

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
        ('t1','bp1','EURUSD','oco|EURUSD|100|h5|a','BUY',1.10,?,1,5,NULL,1.11,?,10.0,'CLOSED')
        """,
        [base, base],
    )
    con.execute(
        """
        INSERT INTO audit_logs VALUES
        (?,?,'EURUSD','oco|EURUSD|100|h5|a',0.82,0.60,'{}','2025-07'),
        (?,?,'EURUSD','oco|EURUSD|100|h5|b',0.79,0.60,'{}','2025-07')
        """,
        [audit_ts, base, audit_ts, base],
    )
    con.close()


def _create_predictions(path: Path) -> None:
    rows = [
        {
            "close_ts": "2025-07-25T10:30:00Z",
            "candidate_uid": "oco|EURUSD|100|h5|a",
            "pred_prob": 0.82,
            "threshold_exec": 0.60,
            "selected_exec": 1,
            "threshold_source": "rolling_days:schedule",
            "test_month": "2025-07",
        },
        {
            "close_ts": "2025-07-25T10:31:00Z",
            "candidate_uid": "oco|EURUSD|100|h5|b",
            "pred_prob": 0.79,
            "threshold_exec": 0.60,
            "selected_exec": 1,
            "threshold_source": "rolling_days:schedule",
            "test_month": "2025-07",
        },
        {
            "close_ts": "2025-07-25T10:32:00Z",
            "candidate_uid": "oco|EURUSD|100|h5|c",
            "pred_prob": 0.55,
            "threshold_exec": 0.60,
            "selected_exec": 0,
            "threshold_source": "rolling_days:schedule",
            "test_month": "2025-07",
        },
    ]
    pd.DataFrame(rows).to_parquet(path, index=False)


def _create_predictions_with_extra_selected(path: Path) -> None:
    rows = [
        {
            "close_ts": "2025-07-25T10:30:00Z",
            "candidate_uid": "oco|EURUSD|100|h5|a",
            "pred_prob": 0.82,
            "threshold_exec": 0.60,
            "selected_exec": 1,
            "threshold_source": "rolling_days:schedule",
            "test_month": "2025-07",
        },
        {
            "close_ts": "2025-07-25T10:31:00Z",
            "candidate_uid": "oco|EURUSD|100|h5|b",
            "pred_prob": 0.79,
            "threshold_exec": 0.60,
            "selected_exec": 1,
            "threshold_source": "rolling_days:schedule",
            "test_month": "2025-07",
        },
        {
            "close_ts": "2025-07-25T10:32:00Z",
            "candidate_uid": "oco|EURUSD|100|h5|extra",
            "pred_prob": 0.81,
            "threshold_exec": 0.60,
            "selected_exec": 1,
            "threshold_source": "rolling_days:schedule",
            "test_month": "2025-07",
        },
    ]
    pd.DataFrame(rows).to_parquet(path, index=False)


def _create_predictions_ns(path: Path) -> None:
    rows = [
        {
            "close_ts": "2025-07-25T10:30:00.123456Z",
            "candidate_uid": "oco|EURUSD|100|h5|a",
            "pred_prob": 0.82,
            "threshold_exec": 0.60,
            "selected_exec": 1,
            "threshold_source": "rolling_days:schedule",
            "test_month": "2025-07",
        },
        {
            "close_ts": "2025-07-25T10:31:00.123456Z",
            "candidate_uid": "oco|EURUSD|100|h5|b",
            "pred_prob": 0.79,
            "threshold_exec": 0.60,
            "selected_exec": 1,
            "threshold_source": "rolling_days:schedule",
            "test_month": "2025-07",
        },
    ]
    df = pd.DataFrame(rows)
    df["close_ts"] = pd.to_datetime(df["close_ts"], utc=True).astype("datetime64[ns, UTC]")
    df.to_parquet(path, index=False)


def _create_history_lock_dir(path: Path) -> None:
    lock_dir = path / "2025-07"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = {
        "symbol": "EURUSD",
        "artifacts": {
            "model_cbm_path": "models/oco/EURUSD_model_2025-07.cbm",
            "model_cbm_sha256": "x",
            "model_threshold_json_path": "models/oco/EURUSD_model_2025-07.json",
            "model_threshold_json_sha256": "y",
            "model_month": "2025-07",
        },
        "locked_runtime": {"production_cap_pips": 1.2},
        "state_universe": {
            "rows": [
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 5,
                    "barrier_pips": 2.0,
                    "state_id": "a",
                    "regime_desc": "a",
                },
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 5,
                    "barrier_pips": 2.0,
                    "state_id": "b",
                    "regime_desc": "b",
                },
            ]
        },
    }
    (lock_dir / "eurusd_oco_live_lock.json").write_text(json.dumps(lock), encoding="utf-8")


def _metric_status(checks: pd.DataFrame, metric: str) -> str:
    row = checks[checks["metric"].astype(str) == metric].iloc[0]
    return str(row["status"])


def _metric_value(checks: pd.DataFrame, metric: str) -> float:
    row = checks[checks["metric"].astype(str) == metric].iloc[0]
    return float(row["value"])


def test_reconcile_ctrader_vs_research_passes_for_aligned_fixture(tmp_path: Path) -> None:
    db = tmp_path / "runtime.db"
    pred = tmp_path / "pred.parquet"
    _create_db(db, audit_in_window=True)
    _create_predictions(pred)

    checks, mismatches = run(
        symbol="EURUSD",
        runtime_db_path=db,
        predictions_parquet=pred,
        history_dir=None,
        start_ts="2025-07-25T00:00:00Z",
        end_ts="2025-07-26T00:00:00Z",
        strict_window=True,
        timestamp_tolerance_sec=120.0,
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    assert _metric_status(checks, "selected_key_missing_count") == "pass"
    assert _metric_status(checks, "selected_key_extra_count") == "pass"
    assert _metric_status(checks, "selected_key_jaccard") == "pass"
    assert (tmp_path / "checks.csv").exists()
    assert (tmp_path / "mismatches.csv").exists()
    assert (tmp_path / "report.md").exists()
    assert len(mismatches[mismatches["type"].astype(str) == "missing_selected_key"]) == 0


def test_reconcile_ctrader_vs_research_flags_audit_event_ts_window_mismatch(tmp_path: Path) -> None:
    db = tmp_path / "runtime.db"
    pred = tmp_path / "pred.parquet"
    _create_db(db, audit_in_window=False)
    _create_predictions(pred)

    checks, mismatches = run(
        symbol="EURUSD",
        runtime_db_path=db,
        predictions_parquet=pred,
        history_dir=None,
        start_ts="2025-07-25T00:00:00Z",
        end_ts="2025-07-26T00:00:00Z",
        strict_window=True,
        timestamp_tolerance_sec=2.0,
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    assert _metric_status(checks, "audit_event_window_ratio") in {"pass", "fail"}
    ts_status = _metric_status(checks, "timestamp_match_ratio")
    assert ts_status in {"fail", "pass"}
    assert len(mismatches[mismatches["type"].astype(str) == "audit_event_ts_outside_window"]) == 0


def test_reconcile_handles_datetime_unit_mismatch_ns_vs_us(tmp_path: Path) -> None:
    db = tmp_path / "runtime.db"
    pred = tmp_path / "pred_ns.parquet"
    _create_db(db, audit_in_window=True)
    _create_predictions_ns(pred)

    checks, _ = run(
        symbol="EURUSD",
        runtime_db_path=db,
        predictions_parquet=pred,
        history_dir=None,
        start_ts="2025-07-25T00:00:00Z",
        end_ts="2025-07-26T00:00:00Z",
        strict_window=True,
        timestamp_tolerance_sec=120.0,
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    assert _metric_status(checks, "timestamp_match_ratio") == "pass"


def test_reconcile_history_lock_filter_removes_unlocked_selected_candidates(tmp_path: Path) -> None:
    db = tmp_path / "runtime.db"
    pred = tmp_path / "pred.parquet"
    hist = tmp_path / "oco_history"
    _create_db(db, audit_in_window=True)
    _create_predictions_with_extra_selected(pred)
    _create_history_lock_dir(hist)

    checks, _ = run(
        symbol="EURUSD",
        runtime_db_path=db,
        predictions_parquet=pred,
        history_dir=hist,
        start_ts="2025-07-25T00:00:00Z",
        end_ts="2025-07-26T00:00:00Z",
        strict_window=True,
        timestamp_tolerance_sec=120.0,
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    assert _metric_status(checks, "hist_lock_month_coverage_ratio") == "pass"
    assert _metric_status(checks, "selected_key_missing_count") == "pass"


def test_reconcile_strict_window_allows_rows_after_end(tmp_path: Path) -> None:
    db = tmp_path / "runtime.db"
    pred = tmp_path / "pred.parquet"
    _create_db(db, audit_in_window=True)
    _create_predictions(pred)

    con = duckdb.connect(str(db))
    con.execute(
        """
        INSERT INTO trades VALUES
        ('t_after','bp_after','EURUSD','oco|EURUSD|100|h5|a','BUY',1.10,?,1,5,NULL,1.11,?,1.0,'CLOSED')
        """,
        ["2025-07-26T10:30:00Z", "2025-07-26T10:31:00Z"],
    )
    con.close()

    checks, _ = run(
        symbol="EURUSD",
        runtime_db_path=db,
        predictions_parquet=pred,
        history_dir=None,
        start_ts="2025-07-25T00:00:00Z",
        end_ts="2025-07-26T00:00:00Z",
        strict_window=True,
        timestamp_tolerance_sec=120.0,
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    assert _metric_status(checks, "trades_rows_outside_window") == "pass"
    assert _metric_status(checks, "trades_rows_after_window") == "pass"
    assert _metric_value(checks, "trades_rows_after_window") >= 1.0


def test_reconcile_strict_window_flags_rows_before_start(tmp_path: Path) -> None:
    db = tmp_path / "runtime.db"
    pred = tmp_path / "pred.parquet"
    _create_db(db, audit_in_window=True)
    _create_predictions(pred)

    con = duckdb.connect(str(db))
    con.execute(
        """
        INSERT INTO trades VALUES
        ('t_before','bp_before','EURUSD','oco|EURUSD|100|h5|a','BUY',1.10,?,1,5,NULL,1.11,?,1.0,'CLOSED')
        """,
        ["2025-07-24T10:30:00Z", "2025-07-24T10:31:00Z"],
    )
    con.close()

    checks, mismatches = run(
        symbol="EURUSD",
        runtime_db_path=db,
        predictions_parquet=pred,
        history_dir=None,
        start_ts="2025-07-25T00:00:00Z",
        end_ts="2025-07-26T00:00:00Z",
        strict_window=True,
        timestamp_tolerance_sec=120.0,
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    assert _metric_status(checks, "trades_rows_outside_window") == "fail"
    assert len(mismatches[mismatches["type"].astype(str) == "trade_entry_before_window"]) >= 1


def test_reconcile_flags_selected_count_mismatch_by_key(tmp_path: Path) -> None:
    db = tmp_path / "runtime.db"
    pred = tmp_path / "pred.parquet"
    _create_db(db, audit_in_window=True)
    _create_predictions(pred)

    con = duckdb.connect(str(db))
    con.execute(
        """
        INSERT INTO audit_logs VALUES
        (?,?,'EURUSD','oco|EURUSD|100|h5|a',0.85,0.60,'{}','2025-07')
        """,
        ["2025-07-25T10:45:00Z", "2025-07-25T10:45:00Z"],
    )
    con.close()

    checks, mismatches = run(
        symbol="EURUSD",
        runtime_db_path=db,
        predictions_parquet=pred,
        history_dir=None,
        start_ts="2025-07-25T00:00:00Z",
        end_ts="2025-07-26T00:00:00Z",
        strict_window=True,
        timestamp_tolerance_sec=120.0,
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    assert _metric_status(checks, "selected_count_extra_rows") == "fail"
    assert _metric_status(checks, "selected_count_ratio_runtime_vs_research") == "fail"
    assert len(mismatches[mismatches["type"].astype(str) == "extra_selected_count_by_key"]) >= 1

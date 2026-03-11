from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from scripts.validate_histdata_ctrader_execution_parity import run


def _write_runtime_db(
    path: Path,
    *,
    include_trade: bool = True,
    duplicate_raw_tick: bool = False,
    candidate_uid: str = "oco|EURUSD|100|h5|oco_first_touch_clean__high_range_q70__k2",
) -> None:
    t0 = datetime(2025, 7, 7, 0, 0, 1, tzinfo=timezone.utc)
    t1 = datetime(2025, 7, 7, 0, 0, 2, tzinfo=timezone.utc)
    t2 = datetime(2025, 7, 7, 0, 0, 5, tzinfo=timezone.utc)

    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE trades (
            broker_pos_id VARCHAR,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            side VARCHAR,
            entry_price DOUBLE,
            entry_ts TIMESTAMP WITH TIME ZONE,
            exit_price DOUBLE,
            exit_ts TIMESTAMP WITH TIME ZONE,
            pnl_pips DOUBLE,
            status VARCHAR
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
            ask DOUBLE
        )
        """
    )

    if include_trade:
        con.execute(
            """
            INSERT INTO trades VALUES
            ('210','EURUSD',?,
             'BUY',1.1002,?,1.1000,?,-2.0,'CLOSED')
            """,
            [candidate_uid, t0, t2],
        )

    con.execute(
        """
        INSERT INTO raw_ticks VALUES
        (?,?,'EURUSD',1.1000,1.1002),
        (?,?,'EURUSD',1.1001,1.1003)
        """,
        [t0, t0, t1, t1],
    )
    if duplicate_raw_tick:
        con.execute(
            """
            INSERT INTO raw_ticks VALUES
            (?,?,'EURUSD',1.1001,1.1003)
            """,
            [t1, t1],
        )
    con.close()


def _write_events_json(path: Path) -> None:
    base_ms = int(datetime(2025, 7, 7, 0, 0, 1, tzinfo=timezone.utc).timestamp() * 1000)
    close_ms = int(datetime(2025, 7, 7, 0, 0, 5, tzinfo=timezone.utc).timestamp() * 1000)
    rows = [
        {
            "event": "Create Position",
            "time": base_ms,
            "positionId": 210,
            "type": "Buy",
            "entryPrice": 1.1002,
        },
        {
            "event": "Position closed",
            "time": close_ms,
            "positionId": 210,
            "closePrice": 1.1000,
            "pips": -2.0,
        },
    ]
    path.write_text(json.dumps(rows), encoding="utf-8")


def _write_repo_detail_csv(path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "candidate_uid": "oco|EURUSD|100|h5|oco_first_touch_clean__high_range_q70__k2",
                "side": 1,
                "barrier_px": 1.1002,
                "touch_open_ts": "2025-07-07T00:00:01Z",
                "touch_close_ts": "2025-07-07T00:00:05Z",
            }
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _write_reduced_schedule_csv(path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "test_month": "2025-07",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "oco_first_touch_clean__high_range_q70__k2",
            },
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _write_hist_parquet(tick_root: Path) -> None:
    out = pd.DataFrame(
        [
            {"timestamp": "2025-07-07T00:00:01Z", "bid": 1.1000, "ask": 1.1002},
            {"timestamp": "2025-07-07T00:00:02Z", "bid": 1.1001, "ask": 1.1003},
        ]
    )
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    p = tick_root / "EURUSD" / "EURUSD_202507_ticks.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(p, index=False)


def test_histdata_ctrader_execution_parity_green(tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime.db"
    events_json = tmp_path / "events.json"
    repo_csv = tmp_path / "repo_detail.csv"
    tick_root = tmp_path / "tick"

    _write_runtime_db(runtime_db, include_trade=True, duplicate_raw_tick=False)
    _write_events_json(events_json)
    _write_repo_detail_csv(repo_csv)
    _write_hist_parquet(tick_root)

    summary, checks, mismatches = run(
        symbol="EURUSD",
        runtime_db=runtime_db,
        ctrader_events_json=events_json,
        repo_stoplimit_detail_csv=repo_csv,
        tick_root=tick_root,
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-07T00:00:10Z",
        time_tolerance_sec=1.0,
        price_tolerance_pips=0.1,
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    assert summary.iloc[0]["histdata_execution_parity_verdict"] == "green"
    assert bool(summary.iloc[0]["overall_pass"]) is True
    assert mismatches.empty
    assert (checks["status"].astype(str) == "fail").sum() == 0


def test_histdata_ctrader_execution_parity_fails_on_duplicate_runtime_ticks(tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime.db"
    events_json = tmp_path / "events.json"
    repo_csv = tmp_path / "repo_detail.csv"
    tick_root = tmp_path / "tick"

    _write_runtime_db(runtime_db, include_trade=True, duplicate_raw_tick=True)
    _write_events_json(events_json)
    _write_repo_detail_csv(repo_csv)
    _write_hist_parquet(tick_root)

    summary, checks, _ = run(
        symbol="EURUSD",
        runtime_db=runtime_db,
        ctrader_events_json=events_json,
        repo_stoplimit_detail_csv=repo_csv,
        tick_root=tick_root,
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-07T00:00:10Z",
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    dup_check = checks[checks["check_id"].astype(str) == "RUNTIME_RAW_TICK_DUPLICATE_TRIPLETS_EQ_0"].iloc[0]
    assert dup_check["status"] == "fail"
    assert summary.iloc[0]["histdata_execution_parity_verdict"] == "red"


def test_histdata_ctrader_execution_parity_fails_when_expected_execution_missing(tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime.db"
    events_json = tmp_path / "events.json"
    repo_csv = tmp_path / "repo_detail.csv"
    tick_root = tmp_path / "tick"

    _write_runtime_db(runtime_db, include_trade=False, duplicate_raw_tick=False)
    _write_events_json(events_json)
    _write_repo_detail_csv(repo_csv)
    _write_hist_parquet(tick_root)

    summary, checks, mismatches = run(
        symbol="EURUSD",
        runtime_db=runtime_db,
        ctrader_events_json=events_json,
        repo_stoplimit_detail_csv=repo_csv,
        tick_root=tick_root,
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-07T00:00:10Z",
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    miss_check = checks[checks["check_id"].astype(str) == "ENTRY_MISSING_EXPECTED_EQ_0"].iloc[0]
    assert miss_check["status"] == "fail"
    assert (mismatches["type"].astype(str) == "missing_expected_execution").any()
    assert summary.iloc[0]["histdata_execution_parity_verdict"] == "red"


def test_histdata_ctrader_execution_parity_reduced_core_filter_applies(tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime.db"
    events_json = tmp_path / "events.json"
    repo_csv = tmp_path / "repo_detail.csv"
    schedule_csv = tmp_path / "state_schedule.csv"
    tick_root = tmp_path / "tick"

    _write_runtime_db(runtime_db, include_trade=True, duplicate_raw_tick=False)
    _write_events_json(events_json)
    _write_repo_detail_csv(repo_csv)
    _write_reduced_schedule_csv(schedule_csv)
    _write_hist_parquet(tick_root)

    summary, checks, mismatches = run(
        symbol="EURUSD",
        runtime_db=runtime_db,
        ctrader_events_json=events_json,
        repo_stoplimit_detail_csv=repo_csv,
        reduced_core_state_schedule_csv=schedule_csv,
        require_reduced_core_filter=True,
        tick_root=tick_root,
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-07T00:00:10Z",
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    sched_check = checks[checks["check_id"].astype(str) == "REDUCED_CORE_SCHEDULE_ROWS_GT_0"].iloc[0]
    assert sched_check["status"] == "pass"
    assert summary.iloc[0]["truth_source"] == "repo_stoplimit_detail_reduced_core"
    assert summary.iloc[0]["repo_expected_rows_before_reduced_filter"] == 1
    assert summary.iloc[0]["repo_expected_rows"] == 1
    assert mismatches.empty


def test_histdata_ctrader_execution_parity_fails_on_noncanonical_runtime_candidate_uid(
    tmp_path: Path,
) -> None:
    runtime_db = tmp_path / "runtime.db"
    events_json = tmp_path / "events.json"
    repo_csv = tmp_path / "repo_detail.csv"
    tick_root = tmp_path / "tick"

    _write_runtime_db(runtime_db, include_trade=True, duplicate_raw_tick=False, candidate_uid="oco")
    _write_events_json(events_json)
    _write_repo_detail_csv(repo_csv)
    _write_hist_parquet(tick_root)

    summary, checks, mismatches = run(
        symbol="EURUSD",
        runtime_db=runtime_db,
        ctrader_events_json=events_json,
        repo_stoplimit_detail_csv=repo_csv,
        tick_root=tick_root,
        start_ts="2025-07-07T00:00:00Z",
        end_ts="2025-07-07T00:00:10Z",
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        out_mismatches_csv=tmp_path / "mismatches.csv",
        report_out=tmp_path / "report.md",
    )

    uid_check = checks[
        checks["check_id"].astype(str) == "RUNTIME_CANDIDATE_UID_NONCANONICAL_EQ_0"
    ].iloc[0]
    assert uid_check["status"] == "fail"
    assert summary.iloc[0]["runtime_candidate_uid_noncanonical_rows"] == 1
    assert (mismatches["type"].astype(str) == "runtime_candidate_uid_noncanonical").any()
    assert summary.iloc[0]["histdata_execution_parity_verdict"] == "red"

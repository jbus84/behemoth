from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from scripts.evaluate_ftmo_challenge_run import evaluate_session


def _runtime_db(path: Path) -> None:
    con = duckdb.connect(str(path))
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
                status VARCHAR,
                run_id VARCHAR
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
            CREATE TABLE ftmo_account_snapshots (
                snapshot_ts TIMESTAMP WITH TIME ZONE,
                symbol VARCHAR,
                balance DOUBLE,
                equity DOUBLE
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
    finally:
        con.close()


def _session(path: Path, runtime_db: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "run_id": "eurusd_ftmo_case",
                "symbol": "EURUSD",
                "source": "histdata",
                "source_root": "/tmp/tick",
                "runtime_db": str(runtime_db),
                "start_ts": "2025-07-07T00:00:00Z",
                "ftmo_enabled": True,
                "ftmo_rules_path": "configs/research/governance/ftmo/ftmo_rules.yaml",
                "ftmo_profile_id": "ftmo_10k_challenge_2step",
                "ftmo_phase_mode": "full_lifecycle",
                "ftmo_economics_mode": "repo_overlay",
                "requested_lot_size": 1.0,
                "surface": "surrogate",
            }
        ),
        encoding="utf-8",
    )


def test_evaluate_session_reports_in_progress_when_target_hit_before_min_days(tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime.db"
    _runtime_db(runtime_db)
    con = duckdb.connect(str(runtime_db))
    try:
        con.execute(
            """
            INSERT INTO trades VALUES
            ('t1', 'p1', 'EURUSD', 'cand_a', 'Buy', 1.1000, '2025-07-07T10:00:00Z', 1, 6, NULL, 1.1120, '2025-07-07T12:00:00Z', 120.0, 'CLOSED', 'eurusd_ftmo_case')
            """
        )
        con.execute(
            """
            INSERT INTO ftmo_risk_reservations VALUES
            ('r1', '2025-07-07T10:00:00Z', '2025-07-07T12:00:00Z', 'EURUSD', 'cand_a', 'p1', 'RELEASED', 100.0, 3.0, 1.2, 0.4, 100000.0, 'Buy', 'predict_allocator')
            """
        )
    finally:
        con.close()

    session_path = tmp_path / "session.json"
    _session(session_path, runtime_db)

    out = evaluate_session(session_path=session_path)
    summary = pd.read_csv(out["ftmo_challenge_summary_csv"])

    assert summary.loc[0, "overall_verdict"] == "in_progress"
    assert summary.loc[0, "phase1_verdict"] == "in_progress"
    assert summary.loc[0, "realized_net_profit_ccy"] > 1000.0
    assert summary.loc[0, "ftmo_trade_cost_gate_mode"] == "warn"
    assert summary.loc[0, "gross_profit_pips"] == 120.0
    assert summary.loc[0, "net_profit_pips_after_ftmo"] == 119.5


def test_evaluate_session_reports_daily_loss_failure_from_snapshots(tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime.db"
    _runtime_db(runtime_db)
    con = duckdb.connect(str(runtime_db))
    try:
        con.execute(
            """
            INSERT INTO ftmo_account_snapshots VALUES
            ('2025-07-07T00:05:00Z', 'EURUSD', 10000.0, 10000.0),
            ('2025-07-07T14:00:00Z', 'EURUSD', 10000.0, 9490.0)
            """
        )
    finally:
        con.close()

    session_path = tmp_path / "session.json"
    _session(session_path, runtime_db)

    out = evaluate_session(session_path=session_path)
    summary = pd.read_csv(out["ftmo_challenge_summary_csv"])
    daily = pd.read_csv(out["ftmo_daily_ledger_csv"])

    assert summary.loc[0, "overall_verdict"] == "failed"
    assert daily.loc[0, "daily_loss_used_ccy"] >= 500.0
    assert daily.loc[0, "violation_code"] == "FTMO_DAILY_LOSS_LIMIT_BREACH"


def test_evaluate_session_reports_two_step_pass(tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime.db"
    _runtime_db(runtime_db)
    con = duckdb.connect(str(runtime_db))
    try:
        trade_rows = []
        res_rows = []
        for idx, (day, pips) in enumerate(
            [
                ("2025-07-07", 31.0),
                ("2025-07-08", 31.0),
                ("2025-07-09", 31.0),
                ("2025-07-10", 31.0),
                ("2025-07-11", 16.0),
                ("2025-07-12", 16.0),
                ("2025-07-13", 16.0),
                ("2025-07-14", 16.0),
            ],
            start=1,
        ):
            trade_rows.append(
                f"('t{idx}', 'p{idx}', 'EURUSD', 'cand_{idx}', 'Buy', 1.1000, '{day}T10:00:00Z', 1, 6, NULL, 1.1000, '{day}T12:00:00Z', {pips}, 'CLOSED', 'eurusd_ftmo_case')"
            )
            res_rows.append(
                f"('r{idx}', '{day}T10:00:00Z', '{day}T12:00:00Z', 'EURUSD', 'cand_{idx}', 'p{idx}', 'RELEASED', 100.0, 3.0, 1.2, 0.4, 100000.0, 'Buy', 'predict_allocator')"
            )
        con.execute("INSERT INTO trades VALUES " + ", ".join(trade_rows))
        con.execute("INSERT INTO ftmo_risk_reservations VALUES " + ", ".join(res_rows))
    finally:
        con.close()

    session_path = tmp_path / "session.json"
    _session(session_path, runtime_db)

    out = evaluate_session(session_path=session_path)
    summary = pd.read_csv(out["ftmo_challenge_summary_csv"])
    phases = pd.read_csv(out["ftmo_daily_ledger_csv"])

    assert summary.loc[0, "overall_verdict"] == "passed"
    assert summary.loc[0, "phase1_verdict"] == "passed"
    assert summary.loc[0, "phase2_verdict"] == "passed"
    assert summary.loc[0, "phases_passed"] == 2
    assert phases["phase_id"].nunique() == 2

"""Tests for scripts.diagnose_live_audit."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest


def _make_synthetic_db(tmp_path: Path, *, with_predict_evaluations: bool = True) -> Path:
    db_path = tmp_path / "live_state.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    if with_predict_evaluations:
        con.execute(
            """
            CREATE TABLE predict_evaluations (
                event_ts TIMESTAMP WITH TIME ZONE,
                close_ts TIMESTAMP WITH TIME ZONE,
                symbol VARCHAR,
                candidate_uid VARCHAR,
                pred_prob DOUBLE,
                threshold DOUBLE,
                preselected_exec INTEGER,
                selected_exec INTEGER,
                threshold_blocked BOOLEAN,
                threshold_block_reason VARCHAR,
                risk_blocked BOOLEAN,
                risk_block_reason VARCHAR,
                model_month VARCHAR,
                run_id VARCHAR
            )
            """
        )
        rows = [
            (
                "2026-03-23T10:00:00Z",
                "2026-03-23T10:05:00Z",
                "GBPUSD",
                "cand-1",
                0.41,
                0.50,
                0,
                0,
                True,
                "THRESHOLD_TOO_LOW",
                False,
                None,
                "2026-02",
                "jforex_live",
            ),
            (
                "2026-03-23T10:01:00Z",
                "2026-03-23T10:06:00Z",
                "GBPUSD",
                "cand-2",
                0.64,
                0.50,
                1,
                0,
                False,
                None,
                True,
                "RISK_BREACH",
                "2026-02",
                "jforex_live",
            ),
            (
                "2026-03-23T10:02:00Z",
                "2026-03-23T10:07:00Z",
                "GBPUSD",
                "cand-3",
                0.81,
                0.50,
                1,
                1,
                False,
                None,
                False,
                None,
                "2026-02",
                "jforex_live",
            ),
        ]
        con.executemany("INSERT INTO predict_evaluations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

    con.execute(
        """
        CREATE TABLE account_risk_allocator_events (
            event_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            status VARCHAR,
            block_reason VARCHAR,
            reservation_id VARCHAR
        )
        """
    )
    con.executemany(
        "INSERT INTO account_risk_allocator_events VALUES (?, ?, ?, ?, ?)",
        [
            ("2026-03-23T10:00:00Z", "GBPUSD", "ADMITTED", None, "res-1"),
            ("2026-03-23T10:01:00Z", "GBPUSD", "BLOCKED", "ACCOUNT_RISK_RESERVED_BUDGET_EXCEEDED", "res-2"),
        ],
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
    con.executemany(
        "INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("2026-03-23T10:00:00Z", "2026-03-23T10:05:00Z", "GBPUSD", "cand-1", 0.41, 0.50, "{}", "2026-02", "jforex_live"),
            ("2026-03-23T10:01:00Z", "2026-03-23T10:06:00Z", "GBPUSD", "cand-2", 0.64, 0.50, "{}", "2026-02", "jforex_live"),
            ("2026-03-23T10:02:00Z", "2026-03-23T10:07:00Z", "GBPUSD", "cand-3", 0.81, 0.50, "{}", "2026-02", "jforex_live"),
        ],
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
            close_reason VARCHAR,
            run_id VARCHAR
        )
        """
    )
    con.executemany(
        "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("t-1", "bp-1", "GBPUSD", "cand-3", "BUY", 1.3, "2026-03-23T10:02:00Z", 1, 6, 2, 1.31, "2026-03-23T10:08:00Z", 2.0, "CLOSED", "TP", "jforex_live"),
            ("t-2", "bp-2", "GBPUSD", "cand-2", "BUY", 1.3, "2026-03-23T10:03:00Z", 2, 6, 3, 1.29, "2026-03-23T10:09:00Z", -1.5, "CLOSED", "SL", "jforex_live"),
            ("t-3", "bp-3", "GBPUSD", "cand-1", "BUY", 1.3, "2026-03-23T10:04:00Z", 3, 6, None, None, None, None, "OPEN", None, "jforex_live"),
        ],
    )

    con.close()
    return db_path


def test_checkpoint_helper_connects_even_when_checkpoint_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = _make_synthetic_db(tmp_path)
    import requests
    from scripts.diagnose_live_audit import checkpoint_and_connect

    calls: list[tuple[str, bool]] = []

    class _Response:
        def raise_for_status(self) -> None:
            raise requests.RequestException("boom")

    def fake_get(url: str, timeout: int) -> _Response:
        calls.append((url, timeout == 5))
        return _Response()

    real_connect = duckdb.connect

    def fake_connect(path: str, read_only: bool = False):
        calls.append((path, read_only))
        return real_connect(path, read_only=read_only)

    monkeypatch.setattr("scripts.diagnose_live_audit.requests.get", fake_get)
    monkeypatch.setattr("scripts.diagnose_live_audit.duckdb.connect", fake_connect)

    con = checkpoint_and_connect("http://localhost:8000", str(db_path))
    try:
        assert calls[0] == ("http://localhost:8000/state/checkpoint", True)
        assert calls[1] == (str(db_path), True)
        assert con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 3
    finally:
        con.close()


def test_has_predict_evaluations_true_and_false(tmp_path: Path) -> None:
    from scripts.diagnose_live_audit import _has_predict_evaluations

    con_true = duckdb.connect(str(_make_synthetic_db(tmp_path / "with_eval")))
    con_false = duckdb.connect(str(_make_synthetic_db(tmp_path / "without_eval", with_predict_evaluations=False)))
    try:
        assert _has_predict_evaluations(con_true, "jforex_live") is True
        assert _has_predict_evaluations(con_false, "jforex_live") is False
    finally:
        con_true.close()
        con_false.close()


def test_section_funnel_uses_predict_evaluations(tmp_path: Path) -> None:
    con = duckdb.connect(str(_make_synthetic_db(tmp_path)))
    try:
        from scripts.diagnose_live_audit import _section_funnel

        lines = _section_funnel(con, "jforex_live", True)
        text = "\n".join(lines)
        assert "Prediction Funnel" in text
        assert "predict_evaluations" in text
        assert "| GBPUSD   |                   3 |                    2 |                 1 |        3 |" in text
    finally:
        con.close()


def test_section_funnel_falls_back_without_predict_evaluations(tmp_path: Path) -> None:
    con = duckdb.connect(str(_make_synthetic_db(tmp_path, with_predict_evaluations=False)))
    try:
        from scripts.diagnose_live_audit import _section_funnel

        lines = _section_funnel(con, "jforex_live", False)
        text = "\n".join(lines)
        assert "fallback" in text.lower()
        assert "account_risk_allocator_events" in text
        assert "admitted" in text.lower()
        assert "blocked" in text.lower()
    finally:
        con.close()


def test_section_score_distribution_uses_predict_evaluations(tmp_path: Path) -> None:
    con = duckdb.connect(str(_make_synthetic_db(tmp_path)))
    try:
        from scripts.diagnose_live_audit import _section_score_distribution

        lines = _section_score_distribution(con, "jforex_live", True)
        text = "\n".join(lines)
        assert "Score Distribution" in text
        assert "| GBPUSD   |   3 |         0.5 | 0.525 |  0.64 | 0.725 | 0.776 | 0.793 | 0.807 |" in text
    finally:
        con.close()


def test_section_block_reasons_uses_predict_evaluations(tmp_path: Path) -> None:
    con = duckdb.connect(str(_make_synthetic_db(tmp_path)))
    try:
        from scripts.diagnose_live_audit import _section_block_reasons

        lines = _section_block_reasons(con, "jforex_live", True)
        text = "\n".join(lines)
        assert "Block Reason Breakdown" in text
        assert "THRESHOLD_TOO_LOW" in text
        assert "RISK_BREACH" in text
    finally:
        con.close()


def test_section_trade_outcomes_reports_closed_trades(tmp_path: Path) -> None:
    con = duckdb.connect(str(_make_synthetic_db(tmp_path)))
    try:
        from scripts.diagnose_live_audit import _section_trade_outcomes

        lines = _section_trade_outcomes(con, "jforex_live")
        text = "\n".join(lines)
        assert "Trade Outcomes" in text
        assert "| GBPUSD   |               2 |      1 | 50.0%      |                 2 |             -1.5 |              0.5 | TP=1, SL=1      |" in text
    finally:
        con.close()


def test_section_trade_outcomes_raises_on_schema_drift(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy_state.db"
    con = duckdb.connect(str(db_path))
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
    finally:
        con.close()

    con = duckdb.connect(str(db_path))
    try:
        from scripts.diagnose_live_audit import _section_trade_outcomes

        with pytest.raises(RuntimeError, match="diagnostic query failed"):
            _section_trade_outcomes(con, "jforex_live")
    finally:
        con.close()

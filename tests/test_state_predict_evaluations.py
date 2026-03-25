from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture
def sm():
    from src.behemoth.runtime.state import StateManager

    state = StateManager()
    yield state
    state.close()


def test_log_predict_evaluation_writes_expected_row(sm):
    event_ts = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)
    close_ts = datetime(2026, 3, 25, 12, 5, tzinfo=timezone.utc)

    sm.log_predict_evaluation(
        event_ts=event_ts,
        close_ts=close_ts,
        symbol="eurusd",
        candidate_uid="cand-001",
        pred_prob="0.875",
        threshold="0.700",
        preselected_exec=True,
        selected_exec=False,
        threshold_blocked=False,
        threshold_block_reason=None,
        risk_blocked=True,
        risk_block_reason="ACCOUNT_RISK_GUARD",
        model_month="2026-03",
        run_id=None,
    )

    row = sm._con.execute(
        """
        SELECT event_ts, close_ts, symbol, candidate_uid, pred_prob, threshold,
               preselected_exec, selected_exec, threshold_blocked, threshold_block_reason,
               risk_blocked, risk_block_reason, model_month, run_id
        FROM predict_evaluations
        """
    ).fetchone()

    assert row[0] == event_ts
    assert row[1] == close_ts
    assert row[2] == "EURUSD"
    assert row[3] == "cand-001"
    assert row[4] == pytest.approx(0.875)
    assert row[5] == pytest.approx(0.700)
    assert row[6] == 1
    assert row[7] == 0
    assert row[8] is False
    assert row[9] is None
    assert row[10] is True
    assert row[11] == "ACCOUNT_RISK_GUARD"
    assert row[12] == "2026-03"
    assert row[13] is None


def test_log_predict_evaluation_does_not_touch_audit_logs(sm):
    sm.log_predict_evaluation(
        event_ts=datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc),
        close_ts=None,
        symbol="GBPUSD",
        candidate_uid="cand-002",
        pred_prob=0.45,
        threshold=0.50,
        preselected_exec=0,
        selected_exec=0,
        threshold_blocked=True,
        threshold_block_reason="THRESHOLD",
        risk_blocked=False,
        risk_block_reason=None,
        model_month="2026-03",
        run_id="run-123",
    )

    audit_rows = sm._con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()
    predict_rows = sm._con.execute("SELECT COUNT(*) FROM predict_evaluations").fetchone()

    assert audit_rows[0] == 0
    assert predict_rows[0] == 1


def test_log_predict_evaluation_orders_all_gate_outcomes_by_event_ts(sm):
    rows = [
        (
            datetime(2026, 3, 25, 12, 20, tzinfo=timezone.utc),
            1,
            1,
        ),
        (
            datetime(2026, 3, 25, 12, 10, tzinfo=timezone.utc),
            1,
            0,
        ),
        (
            datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc),
            0,
            0,
        ),
    ]

    for event_ts, preselected_exec, selected_exec in rows:
        sm.log_predict_evaluation(
            event_ts=event_ts,
            close_ts=None,
            symbol="USDJPY",
            candidate_uid=f"cand-{preselected_exec}{selected_exec}",
            pred_prob=0.8,
            threshold=0.6,
            preselected_exec=preselected_exec,
            selected_exec=selected_exec,
            threshold_blocked=(preselected_exec == 0),
            threshold_block_reason="THRESHOLD" if preselected_exec == 0 else None,
            risk_blocked=(selected_exec == 0 and preselected_exec == 1),
            risk_block_reason="RISK" if selected_exec == 0 and preselected_exec == 1 else None,
            model_month="2026-03",
            run_id="run-456",
        )

    got = sm._con.execute(
        """
        SELECT preselected_exec, selected_exec
        FROM predict_evaluations
        ORDER BY event_ts ASC
        """
    ).fetchall()

    assert got == [(0, 0), (1, 0), (1, 1)]

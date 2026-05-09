"""Test ReservationLifecycle Audit Trail Persistence — DuckDB as authoritative source."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.behemoth.runtime.state import StateManager
from src.behemoth.risk.account import ReservationState


class TestAuditTrailPersistence:
    """Verify audit trail survives StateManager restarts."""

    def test_audit_trail_survives_state_manager_restart(self) -> None:
        """Create reservation, create new StateManager, verify trail persists in DuckDB."""
        with TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            # Session 1: create a reservation
            sm1 = StateManager(persist_path=db_path)
            rid = sm1.create_account_risk_reservation(
                symbol="EURUSD",
                candidate_uid="test_candidate_1",
                reserved_loss_ccy=100.0,
                barrier_pips=50.0,
                cap_pips=25.0,
                cost_est_pips=5.0,
                volume_units=1.0,
                side="BUY",
            )

            # Verify audit trail exists in session 1
            trail_1 = sm1.get_reservation_audit_trail(rid)
            assert trail_1 is not None
            assert len(trail_1) == 1
            assert trail_1[0]["to_status"] == "PENDING"

            # Session 2: create new StateManager, verify trail persists
            sm2 = StateManager(persist_path=db_path)
            trail_2 = sm2.get_reservation_audit_trail(rid)
            assert trail_2 is not None
            assert len(trail_2) == 1
            assert trail_2[0]["to_status"] == "PENDING"

    def test_audit_trail_records_all_transitions(self) -> None:
        """Verify all transitions are recorded: PENDING → OPEN → CLOSED."""
        sm = StateManager()
        rid = sm.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="test_candidate_2",
            reserved_loss_ccy=100.0,
            barrier_pips=50.0,
            cap_pips=25.0,
            cost_est_pips=5.0,
            volume_units=1.0,
            side="BUY",
        )

        # Verify initial PENDING transition
        trail = sm.get_reservation_audit_trail(rid)
        assert len(trail) == 1
        assert trail[0]["from_status"] is None
        assert trail[0]["to_status"] == "PENDING"

        # Transition to OPEN
        sm.transition_account_risk_reservation(
            rid,
            ReservationState.OPEN,
            broker_pos_id="broker_123",
            reason="order_filled",
        )

        # Verify PENDING → OPEN transition
        trail = sm.get_reservation_audit_trail(rid)
        assert len(trail) == 2
        assert trail[1]["from_status"] == "PENDING"
        assert trail[1]["to_status"] == "OPEN"
        assert trail[1]["broker_pos_id"] == "broker_123"
        assert trail[1]["reason"] == "order_filled"

        # Transition to CLOSED
        sm.transition_account_risk_reservation(
            rid,
            ReservationState.CLOSED,
            reason="target_hit",
        )

        # Verify all three transitions
        trail = sm.get_reservation_audit_trail(rid)
        assert len(trail) == 3
        assert trail[0]["to_status"] == "PENDING"
        assert trail[1]["to_status"] == "OPEN"
        assert trail[2]["from_status"] == "OPEN"
        assert trail[2]["to_status"] == "CLOSED"
        assert trail[2]["reason"] == "target_hit"

    def test_audit_trail_unknown_id_returns_none(self) -> None:
        """Verify unknown reservation IDs return None."""
        sm = StateManager()
        trail = sm.get_reservation_audit_trail("unknown_id")
        assert trail is None

    def test_audit_trail_timestamp_ordering(self) -> None:
        """Verify audit trail events are ordered by timestamp (ASC)."""
        sm = StateManager()
        rid = sm.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="test_candidate_3",
            reserved_loss_ccy=100.0,
            barrier_pips=50.0,
            cap_pips=25.0,
            cost_est_pips=5.0,
            volume_units=1.0,
            side="BUY",
        )

        sm.transition_account_risk_reservation(rid, ReservationState.OPEN)
        sm.transition_account_risk_reservation(rid, ReservationState.CLOSED)

        trail = sm.get_reservation_audit_trail(rid)
        assert len(trail) == 3

        # Verify timestamps are monotonically increasing
        for i in range(len(trail) - 1):
            ts_current = trail[i]["event_ts"]
            ts_next = trail[i + 1]["event_ts"]
            assert ts_current <= ts_next

    def test_audit_trail_with_none_reason(self) -> None:
        """Verify transitions with None reason are recorded correctly."""
        sm = StateManager()
        rid = sm.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="test_candidate_4",
            reserved_loss_ccy=100.0,
            barrier_pips=50.0,
            cap_pips=25.0,
            cost_est_pips=5.0,
            volume_units=1.0,
            side="BUY",
        )

        # Transition without reason
        sm.transition_account_risk_reservation(rid, ReservationState.OPEN)

        trail = sm.get_reservation_audit_trail(rid)
        assert len(trail) == 2
        # Second event should have None reason
        assert trail[1]["reason"] is None

    def test_cache_and_db_consistency(self) -> None:
        """Verify cache and DB remain consistent across transitions."""
        with TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            sm = StateManager(persist_path=db_path)
            rid = sm.create_account_risk_reservation(
                symbol="EURUSD",
                candidate_uid="test_candidate_5",
                reserved_loss_ccy=100.0,
                barrier_pips=50.0,
                cap_pips=25.0,
                cost_est_pips=5.0,
                volume_units=1.0,
                side="BUY",
            )

            # Get trail from cache (same session)
            trail_cache = sm.get_reservation_audit_trail(rid)

            # Create new StateManager to read from DB
            sm2 = StateManager(persist_path=db_path)
            trail_db = sm2.get_reservation_audit_trail(rid)

            # Should match
            assert trail_cache == trail_db

            # Do a transition in original manager
            sm.transition_account_risk_reservation(rid, ReservationState.OPEN)
            trail_cache_2 = sm.get_reservation_audit_trail(rid)

            # Create another StateManager and verify new transition is in DB
            sm3 = StateManager(persist_path=db_path)
            trail_db_2 = sm3.get_reservation_audit_trail(rid)

            assert trail_cache_2 == trail_db_2
            assert len(trail_db_2) == len(trail_cache_2) == 2

    def test_migration_recovery_from_cache(self) -> None:
        """Verify cache-only data is migrated to DB when accessed in a new session."""
        with TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            # Session 1: create and transition (data only in cache + DB)
            sm1 = StateManager(persist_path=db_path)
            rid = sm1.create_account_risk_reservation(
                symbol="EURUSD",
                candidate_uid="test_candidate_6",
                reserved_loss_ccy=100.0,
                barrier_pips=50.0,
                cap_pips=25.0,
                cost_est_pips=5.0,
                volume_units=1.0,
                side="BUY",
            )
            sm1.transition_account_risk_reservation(rid, ReservationState.OPEN)

            trail_1 = sm1.get_reservation_audit_trail(rid)
            assert len(trail_1) == 2

            # Session 2: query the trail (should trigger migration if needed)
            sm2 = StateManager(persist_path=db_path)
            trail_2 = sm2.get_reservation_audit_trail(rid)

            # Should have both events
            assert len(trail_2) == 2
            assert trail_2[0]["to_status"] == "PENDING"
            assert trail_2[1]["to_status"] == "OPEN"

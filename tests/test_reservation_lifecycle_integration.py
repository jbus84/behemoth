"""Integration tests for ReservationLifecycle in StateManager."""

from datetime import datetime, timezone

from src.behemoth.risk.account import ReservationState
from src.behemoth.runtime.state import StateManager


class TestReservationLifecycleIntegration:
    """Verify lifecycle tracking is wired into StateManager."""

    def test_create_reservation_initializes_lifecycle(self) -> None:
        """Creating a reservation should instantiate lifecycle in cache."""
        mgr = StateManager()
        rid = mgr.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="cand_123",
            reserved_loss_ccy=100.0,
            barrier_pips=50.0,
            cap_pips=75.0,
            cost_est_pips=10.0,
            volume_units=1000.0,
        )
        trail = mgr.get_reservation_audit_trail(rid)
        assert trail is not None
        assert len(trail) >= 1
        assert trail[0]["to_state"] == ReservationState.PENDING.value
        mgr.close()

    def test_promote_adds_open_transition(self) -> None:
        """Promoting a reservation should add OPEN transition to lifecycle."""
        mgr = StateManager()
        rid = mgr.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="cand_456",
            reserved_loss_ccy=150.0,
            barrier_pips=60.0,
            cap_pips=90.0,
            cost_est_pips=15.0,
            volume_units=1500.0,
        )
        mgr.promote_account_risk_reservation(
            broker_pos_id="broker_789", reservation_id=rid
        )
        trail = mgr.get_reservation_audit_trail(rid)
        assert trail is not None
        assert len(trail) >= 2
        open_transitions = [t for t in trail if t["to_state"] == ReservationState.OPEN.value]
        assert len(open_transitions) == 1
        mgr.close()

    def test_release_adds_released_terminal_transition(self) -> None:
        """Releasing a reservation should add RELEASED terminal transition."""
        mgr = StateManager()
        rid = mgr.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="cand_789",
            reserved_loss_ccy=200.0,
            barrier_pips=70.0,
            cap_pips=100.0,
            cost_est_pips=20.0,
            volume_units=2000.0,
        )
        mgr.release_account_risk_reservation(reservation_id=rid, reason="manual")
        trail = mgr.get_reservation_audit_trail(rid)
        assert trail is not None
        assert trail[-1]["to_state"] == ReservationState.RELEASED.value
        assert "reason" in trail[-1]
        mgr.close()

    def test_expire_stale_adds_expired_terminal_transition(self) -> None:
        """Expiring stale reservations should add EXPIRED transitions."""
        mgr = StateManager()
        rid = mgr.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="cand_old",
            reserved_loss_ccy=50.0,
            barrier_pips=40.0,
            cap_pips=60.0,
            cost_est_pips=5.0,
            volume_units=500.0,
        )
        mgr.expire_stale_account_risk_pending_reservations(max_age_seconds=0)
        trail = mgr.get_reservation_audit_trail(rid)
        assert trail is not None
        assert trail[-1]["to_state"] == ReservationState.EXPIRED.value
        mgr.close()

    def test_audit_trail_has_timestamps(self) -> None:
        """Audit trail transitions should have ISO timestamps."""
        mgr = StateManager()
        rid = mgr.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="cand_ts",
            reserved_loss_ccy=80.0,
            barrier_pips=45.0,
            cap_pips=70.0,
            cost_est_pips=12.0,
            volume_units=800.0,
        )
        mgr.promote_account_risk_reservation(broker_pos_id="bp_ts", reservation_id=rid)
        trail = mgr.get_reservation_audit_trail(rid)
        assert trail is not None
        for transition in trail:
            assert "timestamp" in transition
            assert isinstance(transition["timestamp"], str)
            datetime.fromisoformat(transition["timestamp"])
        mgr.close()

    def test_unretracked_reservation_returns_none(self) -> None:
        """Querying audit trail for unknown reservation should return None."""
        mgr = StateManager()
        trail = mgr.get_reservation_audit_trail("unknown_rid")
        assert trail is None
        mgr.close()

    def test_lifecycle_context_preservation(self) -> None:
        """Lifecycle context (loss_ccy, broker_pos_id) should be captured."""
        mgr = StateManager()
        loss = 250.0
        rid = mgr.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="cand_ctx",
            reserved_loss_ccy=loss,
            barrier_pips=80.0,
            cap_pips=120.0,
            cost_est_pips=25.0,
            volume_units=2500.0,
        )
        trail = mgr.get_reservation_audit_trail(rid)
        assert trail is not None
        init_transition = trail[0]
        assert "context" in init_transition
        assert init_transition["context"].get("loss_ccy") == loss
        mgr.close()

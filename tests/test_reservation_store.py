from src.behemoth.runtime.reservation_store import ReservationStore
from src.behemoth.runtime.state_store import InMemoryStateStore


class TestReservationStoreFamily:
    def test_create_reservation_with_family(self):
        store = InMemoryStateStore()
        rs = ReservationStore(store)
        rs.create_account_risk_reservation(
            symbol="EURUSD",
            candidate_uid="directional|eurusd|100|h4|k1",
            reserved_loss_ccy=100.0,
            barrier_pips=10.0,
            cap_pips=1.5,
            cost_est_pips=0.5,
            volume_units=10000.0,
            family="directional",
        )
        snap = rs.list_active_account_risk_reservations(symbol="EURUSD")
        assert len(snap) == 1
        assert snap[0].family == "directional"

    def test_allocator_event_with_family(self):
        store = InMemoryStateStore()
        rs = ReservationStore(store)
        rs.log_account_risk_allocator_event(
            symbol="EURUSD",
            candidate_uid="directional|eurusd|100|h4|k1",
            status="ADMITTED",
            block_reason=None,
            reserved_loss_ccy=50.0,
            requested_volume_units=10000.0,
            pred_prob=0.75,
            threshold_exec=0.5,
            risk_rank_score=0.25,
            reservation_id="res-1",
            family="directional",
        )
        rows = store.execute(
            "SELECT family FROM account_risk_allocator_events WHERE reservation_id = ?",
            ["res-1"],
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "directional"

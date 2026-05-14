
import pytest

from src.behemoth.runtime.reservation_store import ReservationStore
from src.behemoth.runtime.state_store import InMemoryStateStore


class TestReservationStore:
    def test_create_and_list(self) -> None:
        store = InMemoryStateStore()
        rs = ReservationStore(store)
        rid = rs.create_account_risk_reservation(
            symbol="EURUSD", candidate_uid="c1", reserved_loss_ccy=100.0,
            barrier_pips=2.0, cap_pips=3.0, cost_est_pips=0.5, volume_units=10000.0,
        )
        assert rid is not None
        active = rs.list_active_account_risk_reservations()
        assert len(active) == 1
        assert active[0].symbol == "EURUSD"
        assert active[0].status == "PENDING"

    def test_transition_and_sum(self) -> None:
        store = InMemoryStateStore()
        rs = ReservationStore(store)
        rid = rs.create_account_risk_reservation(
            symbol="EURUSD", candidate_uid="c1", reserved_loss_ccy=100.0,
            barrier_pips=2.0, cap_pips=3.0, cost_est_pips=0.5, volume_units=10000.0,
        )
        rs.transition_account_risk_reservation(rid, "OPEN", broker_pos_id="pos1")
        total = rs.sum_active_account_risk_reserved_loss_ccy(include_pending=False, include_open=True)
        assert total == pytest.approx(100.0)

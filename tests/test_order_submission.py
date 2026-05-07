from __future__ import annotations

from src.behemoth.core.schemas import BarrierAction, BarrierActionType
from src.behemoth.runtime.order_submission import prepare_predict_actions


def test_prepare_predict_actions_keeps_open_market_for_broker_submission() -> None:
    action = BarrierAction(
        type=BarrierActionType.OPEN_MARKET,
        symbol="EURUSD",
        candidate_uid="cand",
        scan_id="scan-1",
        side="BUY",
        reservation_id="res-1",
        horizon=6,
    )
    released: list[str] = []

    prepared = prepare_predict_actions(
        [action],
        account_risk_enabled=True,
        release_reservation=lambda reservation_id, reason: released.append(reservation_id),
    )

    assert prepared == [action]
    assert released == []


def test_prepare_predict_actions_releases_reservation_without_broker_submission() -> None:
    action = BarrierAction(
        type=BarrierActionType.RELEASE_RESERVATION,
        symbol="EURUSD",
        candidate_uid="cand",
        scan_id="scan-1",
        reservation_id="res-1",
    )
    released: list[tuple[str, str]] = []

    prepared = prepare_predict_actions(
        [action],
        account_risk_enabled=True,
        release_reservation=lambda reservation_id, reason: released.append((reservation_id, reason)),
    )

    assert prepared == []
    assert released == [("res-1", "barrier_expired")]

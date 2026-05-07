"""Predict-response action preparation for broker submission."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from src.behemoth.core.schemas import BarrierAction, BarrierActionType

ReservationRelease = Callable[[str, str], object]


def prepare_predict_actions(
    actions: Iterable[BarrierAction],
    *,
    account_risk_enabled: bool,
    release_reservation: ReservationRelease,
) -> list[BarrierAction]:
    """Return broker-facing actions and execute Python-side reservation releases."""
    prepared: list[BarrierAction] = []
    for action in actions:
        if action.type == BarrierActionType.RELEASE_RESERVATION:
            if account_risk_enabled and action.reservation_id:
                release_reservation(action.reservation_id, "barrier_expired")
            continue
        prepared.append(action)
    return prepared

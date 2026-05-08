"""Predict-response action preparation for broker submission."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from src.behemoth.core.schemas import BarrierAction, BarrierActionType


class ReservationReleaseCallable(Protocol):
    """Callback protocol for releasing account risk reservations.

    Called when a barrier expires and the reserved capital can be freed.

    Args:
        reservation_id: Unique identifier for the reservation to release
        reason: Reason for release (e.g., "barrier_expired", "manual_cancel")

    Returns:
        None. Raises if release fails (e.g., reservation not found).
    """

    def __call__(self, reservation_id: str, reason: str) -> object:
        ...


def prepare_predict_actions(
    actions: Iterable[BarrierAction],
    *,
    account_risk_enabled: bool,
    release_reservation: ReservationReleaseCallable,
) -> list[BarrierAction]:
    """Prepare predict-response actions for broker submission.

    Filters RELEASE_RESERVATION actions and invokes the release callback.
    Returns only broker-facing actions (OPEN_MARKET, CLOSE_POSITION, etc.).

    Args:
        actions: Iterable of barrier actions from predict response
        account_risk_enabled: Whether account risk reservations are active
        release_reservation: Callback to invoke for each reservation release

    Returns:
        List of actions ready for broker submission
    """
    prepared: list[BarrierAction] = []
    for action in actions:
        if action.type == BarrierActionType.RELEASE_RESERVATION:
            if account_risk_enabled and action.reservation_id:
                release_reservation(action.reservation_id, "barrier_expired")
            continue
        prepared.append(action)
    return prepared

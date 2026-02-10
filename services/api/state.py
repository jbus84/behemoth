from .models import PositionStatus


ALLOWED_TRANSITIONS = {
    PositionStatus.PENDING: {PositionStatus.OPEN, PositionStatus.CANCELLED, PositionStatus.FAILED},
    PositionStatus.OPEN: {PositionStatus.CLOSING, PositionStatus.CLOSED, PositionStatus.FAILED},
    PositionStatus.CLOSING: {PositionStatus.CLOSED, PositionStatus.FAILED},
    PositionStatus.CLOSED: set(),
    PositionStatus.CANCELLED: set(),
    PositionStatus.FAILED: set(),
}


def can_transition(current: PositionStatus, target: PositionStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())

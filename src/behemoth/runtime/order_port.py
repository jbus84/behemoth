"""Order submission protocol for execution adapters.

Decentralizes execution polymorphism: JForex, local testing, noop stubs.
Each adapter owns its full lifecycle including reservation management.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.behemoth.core.schemas import BarrierAction, BarrierActionType


@dataclass(frozen=True)
class SubmissionResult:
    """Result of order submission attempt."""

    success: bool
    order_id: str | None = None
    error_reason: str | None = None


class OrderSubmissionPort(Protocol):
    """Abstract interface for order submission adapters.

    Implementations (JForex, Local, Noop) handle submission and manage
    the full lifecycle: submit → fill confirmation → position tracking → close.

    Each adapter owns reservation release logic (not a callback).
    """

    def submit_open_market(
        self,
        action: BarrierAction,
    ) -> SubmissionResult:
        """Submit an OPEN_MARKET action to broker.

        Transitions reservation from PENDING → OPEN (if successful).
        Manages account risk reservation lifecycle.

        Args:
            action: BarrierAction of type OPEN_MARKET

        Returns:
            SubmissionResult with success flag, order_id, and error reason
        """
        ...

    def submit_close_market(
        self,
        action: BarrierAction,
    ) -> SubmissionResult:
        """Submit a CLOSE_MARKET action to broker.

        Closes an active position. May transition reservation to CLOSED.

        Args:
            action: BarrierAction of type CLOSE_MARKET

        Returns:
            SubmissionResult with success flag and error reason
        """
        ...


class NoopOrderPort:
    """No-op order submission for testing (accepts all, does nothing).

    Used in local testing and dry-run modes.
    """

    def submit_open_market(self, action: BarrierAction) -> SubmissionResult:
        """Accept and log open market order (no-op)."""
        if action.type != BarrierActionType.OPEN_MARKET:
            return SubmissionResult(success=False, error_reason="not an OPEN_MARKET action")
        return SubmissionResult(success=True, order_id=f"noop_order_{action.scan_id}")

    def submit_close_market(self, action: BarrierAction) -> SubmissionResult:
        """Accept and log close market order (no-op)."""
        if action.type != BarrierActionType.CLOSE_MARKET:
            return SubmissionResult(success=False, error_reason="not a CLOSE_MARKET action")
        return SubmissionResult(success=True, order_id=f"noop_order_{action.scan_id}")

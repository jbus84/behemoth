"""Consolidated protocols for StateManager state access.

Defines read-only and write-only interfaces so callers depend on narrow
protocols instead of the full 60-method StateManager god object.

Protocols define behavioral contracts: what callers can rely on without
needing to know implementation details (DuckDB schema, connection pool, etc).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from src.behemoth.core.schemas import BarContext, ModelFeatures


class BarStateReader(Protocol):
    """Read-only interface for bar and feature state.

    Used by feature computation and barrier evaluation: these code paths
    read bars and compute features without modifying state.
    """

    def bar_count(self, symbol: str, bar_ticks: int) -> int:
        """Get number of bars stored for symbol at tick threshold.

        Args:
            symbol: Trading symbol (e.g., 'EURUSD')
            bar_ticks: Bar size in ticks (e.g., 100, 1000, 2000)

        Returns:
            Number of completed tick bars stored
        """
        ...

    def get_latest_bar_context(
        self, symbol: str, bar_ticks: int
    ) -> BarContext | None:
        """Get the most recently completed bar context.

        Args:
            symbol: Trading symbol
            bar_ticks: Bar size in ticks

        Returns:
            BarContext with bid/ask prices, spread, hl metrics, or None if no bars
        """
        ...

    def get_bar_context(
        self,
        symbol: str,
        bar_ticks: int,
        *,
        bar_number: int | None = None,
        side: str | None = None,
    ) -> BarContext | None:
        """Get bar context by bar number or most recent.

        Args:
            symbol: Trading symbol
            bar_ticks: Bar size in ticks
            bar_number: Optional bar index; if None, use latest
            side: Optional side filter ('bid' or 'ask')

        Returns:
            BarContext or None if not found or insufficient history
        """
        ...

    def get_latest_bar(self, symbol: str, bar_ticks: int) -> dict[str, Any] | None:
        """Get latest completed bar as dict (raw schema).

        Args:
            symbol: Trading symbol
            bar_ticks: Bar size in ticks

        Returns:
            Bar dict with OHLC, spread, hl_first, etc., or None
        """
        ...

    def get_latest_close_ts(self, symbol: str) -> datetime | None:
        """Get most recent bar close timestamp.

        Args:
            symbol: Trading symbol

        Returns:
            UTC datetime or None if no bars
        """
        ...

    def compute_features(
        self,
        symbol: str,
        bar_ticks: int,
        horizon: int,
        barrier_pips: float,
    ) -> ModelFeatures | None:
        """Compute feature vector for latest bar.

        Args:
            symbol: Trading symbol
            bar_ticks: Bar size in ticks
            horizon: Bars-to-expiry for feature context
            barrier_pips: Distance in pips for structural features

        Returns:
            16-feature ModelFeatures or None if insufficient warmup
        """
        ...

    def compute_regime_quantiles(
        self, symbol: str, bar_ticks: int
    ) -> dict[str, float]:
        """Compute regime quantiles for filtering.

        Args:
            symbol: Trading symbol
            bar_ticks: Bar size in ticks

        Returns:
            Dict of quantile thresholds
        """
        ...


class AccountRiskStateReader(Protocol):
    """Read-only interface for account risk and reservation state.

    Used by risk evaluation: reads account balance, equity, and active reservations.
    """

    def get_latest_account_risk_snapshot(
        self, symbol: str | None = None
    ) -> dict[str, Any] | None:
        """Get most recent account risk snapshot.

        Args:
            symbol: Symbol to filter by, or None for global snapshot

        Returns:
            Snapshot dict with balance, equity, snapshot_ts, or None
        """
        ...

    def get_account_risk_snapshots_since(
        self, *, since_ts: datetime, symbol: str | None = None
    ) -> list[dict[str, Any]]:
        """Get account risk snapshots since timestamp.

        Args:
            since_ts: Datetime cutoff (UTC)
            symbol: Symbol to filter by, or None for all

        Returns:
            List of snapshots in chronological order
        """
        ...

    def sum_active_account_risk_reserved_loss_ccy(
        self,
        *,
        symbol: str | None = None,
        include_pending: bool = True,
        include_open: bool = True,
    ) -> float:
        """Total reserved loss across active reservations.

        Args:
            symbol: Symbol filter, or None for all symbols
            include_pending: Include PENDING state reservations
            include_open: Include OPEN state reservations

        Returns:
            Sum of reserved_loss_ccy, or 0.0 if no active reservations
        """
        ...

    def list_active_account_risk_reservations(
        self, *, symbol: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all active (PENDING or OPEN) reservations.

        Args:
            symbol: Symbol filter, or None for all

        Returns:
            List of reservation dicts with state, loss, barrier, etc.
        """
        ...


class ReservationWriter(Protocol):
    """Write interface for reservation state machine.

    Used by risk allocation and barrier evaluation to create and transition
    reservations through their lifecycle (PENDING → OPEN → CLOSED/RELEASED/EXPIRED).
    """

    def create_account_risk_reservation(
        self,
        *,
        symbol: str,
        candidate_uid: str,
        reserved_loss_ccy: float,
        barrier_pips: float,
        cap_pips: float,
        cost_est_pips: float,
        volume_units: float,
        side: str | None = None,
        source: str = "predict_allocator",
        status: str = "PENDING",
    ) -> str:
        """Create a new reservation.

        Args:
            symbol: Trading symbol
            candidate_uid: Candidate identifier
            reserved_loss_ccy: Max loss in currency units
            barrier_pips, cap_pips, cost_est_pips: OCO parameters
            volume_units: Position size
            side: BUY or SELL
            source: Origin label (e.g., 'predict_allocator')
            status: Initial state (PENDING or OPEN)

        Returns:
            New reservation_id string
        """
        ...

    def transition_account_risk_reservation(
        self,
        reservation_id: str,
        target_status: str,
        *,
        broker_pos_id: str | None = None,
        reason: str | None = None,
    ) -> str:
        """Transition a reservation to a new state.

        Args:
            reservation_id: Reservation to transition
            target_status: Target state (OPEN, CLOSED, RELEASED, EXPIRED)
            broker_pos_id: Broker position ID if transitioning to OPEN
            reason: Reason for transition (appended to audit trail)

        Returns:
            The new status string
        """
        ...

    def release_account_risk_reservation(
        self,
        *,
        reservation_id: str | None = None,
        broker_pos_id: str | None = None,
        candidate_uid: str | None = None,
        symbol: str | None = None,
        reason: str = "released",
    ) -> int:
        """Release (transition to RELEASED) active reservations matching criteria.

        Args:
            reservation_id, broker_pos_id, candidate_uid, symbol: Match criteria
            reason: Reason for release

        Returns:
            Count of reservations released
        """
        ...

    def expire_stale_account_risk_pending_reservations(
        self, *, max_age_seconds: int
    ) -> int:
        """Expire PENDING reservations older than threshold.

        Args:
            max_age_seconds: Max age in seconds

        Returns:
            Count of reservations expired
        """
        ...

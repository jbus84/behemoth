"""Consolidated read-only protocols for StateManager.

Consolidates BarStateReader, AccountRiskStateReader, RuntimeStateReader
into a single module with clear behavioral contracts (not just signature matching).

These Protocols define what callers need from state without coupling to
StateManager's implementation details.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol


class BarStateReader(Protocol):
    """Read-only interface for bar state access.

    Used by feature computation and barrier evaluation: these code paths
    only read bars, never modify state.
    """

    def get_bar_count(self, symbol: str) -> int:
        """Get number of bars stored for symbol.

        Args:
            symbol: Trading symbol (e.g., 'EURUSD')

        Returns:
            Number of tick bars stored
        """
        ...

    def get_latest_bar_context(self, symbol: str) -> dict[str, Any] | None:
        """Get the most recently completed bar context.

        Args:
            symbol: Trading symbol

        Returns:
            Bar context dict with OHLC, spread, hl_first, or None if no bars
        """
        ...

    def get_bars_by_count(self, symbol: str, count: int) -> list[dict[str, Any]]:
        """Get the most recent N bars for a symbol.

        Args:
            symbol: Trading symbol
            count: Number of bars to retrieve

        Returns:
            List of bar dicts in chronological order
        """
        ...


class AccountRiskStateReader(Protocol):
    """Read-only interface for account risk snapshots.

    Used by risk evaluation: reads account balance, equity, and reservation state.
    """

    def get_latest_account_risk_snapshot(
        self, symbol: str | None
    ) -> dict[str, Any] | None:
        """Get most recent account risk snapshot.

        Args:
            symbol: Symbol to filter by, or None for global snapshot

        Returns:
            Snapshot dict with balance, equity, snapshot_ts, or None
        """
        ...

    def get_account_risk_snapshots_since(
        self, since_ts: datetime, symbol: str | None
    ) -> list[dict[str, Any]]:
        """Get account risk snapshots since timestamp.

        Args:
            since_ts: Datetime cutoff (UTC)
            symbol: Symbol to filter by, or None for all

        Returns:
            List of snapshots in chronological order
        """
        ...


class RuntimeStateReader(Protocol):
    """Read-only interface for full runtime state.

    Union of BarStateReader and AccountRiskStateReader.
    Used by endpoints that need both bar and risk state.
    """

    # Bar reading
    def get_bar_count(self, symbol: str) -> int:
        """Get number of bars for symbol."""
        ...

    def get_latest_bar_context(self, symbol: str) -> dict[str, Any] | None:
        """Get most recent bar context."""
        ...

    def get_bars_by_count(self, symbol: str, count: int) -> list[dict[str, Any]]:
        """Get most recent N bars."""
        ...

    # Account risk reading
    def get_latest_account_risk_snapshot(
        self, symbol: str | None
    ) -> dict[str, Any] | None:
        """Get most recent account risk snapshot."""
        ...

    def get_account_risk_snapshots_since(
        self, since_ts: datetime, symbol: str | None
    ) -> list[dict[str, Any]]:
        """Get account risk snapshots since timestamp."""
        ...

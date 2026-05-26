"""Unified interface for candidate resolution across live and historical governance modes.

Callers use this single interface regardless of governance mode; mode-switching
logic is encapsulated here, reducing 15+ conditionals in server.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from src.behemoth.core.historical_registry import HistoricalCandidateRegistry
from src.behemoth.core.registry import CandidateRegistry, CandidateSpec

if TYPE_CHECKING:
    from src.behemoth.core.bundle_paths import BundlePaths


class UnifiedCandidateRegistry:
    """Mode-aware adapter providing a single interface for both governance paths.

    Implementations of CandidateRegistry and HistoricalCandidateRegistry handle their
    own data loading. This class wraps both and presents a unified API.
    """

    def __init__(
        self,
        live_registry: CandidateRegistry | None,
        historical_registry: HistoricalCandidateRegistry | None,
        is_historical_mode: bool,
        get_latest_month: Callable[[str], str | None] | None = None,
    ) -> None:
        """Initialize with both registries and mode flag.

        Args:
            live_registry: CandidateRegistry for live mode (can be None if historical mode)
            historical_registry: HistoricalCandidateRegistry for historical mode (can be None if live mode)
            is_historical_mode: True if historical governance mode is active
            get_latest_month: Callable to get the latest loaded month for a symbol (historical mode)
        """
        self._live_registry = live_registry
        self._historical_registry = historical_registry
        self._is_historical_mode = is_historical_mode
        self._get_latest_month = get_latest_month or (lambda _: None)

    def get_candidates(self, symbol: str) -> list[CandidateSpec]:
        """Resolve candidates for a symbol in the current governance mode."""
        if self._is_historical_mode:
            if self._historical_registry is None:
                return []
            month = self._get_latest_month(symbol)
            if month is None:
                return []
            return self._historical_registry.get_candidates(symbol, month)
        else:
            if self._live_registry is None:
                return []
            return self._live_registry.get_candidates(symbol)

    def get_cap_pips(self, symbol: str) -> float:
        """Resolve cap_pips for a symbol in the current governance mode."""
        if self._is_historical_mode:
            if self._historical_registry is None:
                return 0.0
            month = self._get_latest_month(symbol)
            if month is None:
                return 0.0
            entry = self._historical_registry.get_entry(symbol, month)
            return float(entry.cap_pips) if entry else 0.0
        else:
            if self._live_registry is None:
                return 0.0
            return self._live_registry.get_cap_pips(symbol)

    def get_bundle_paths(self, symbol: str) -> BundlePaths | None:  # type: ignore
        """Resolve bundle paths for a symbol in the current governance mode."""
        if self._is_historical_mode:
            if self._historical_registry is None:
                return None
            month = self._get_latest_month(symbol)
            if month is None:
                return None
            return self._historical_registry.get_bundle_paths(symbol, month)
        else:
            if self._live_registry is None:
                return None
            return self._live_registry.get_bundle_paths(symbol)

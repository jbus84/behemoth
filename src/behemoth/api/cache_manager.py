"""Unified cache lifecycle management for runtime modules.

Coordinates atomic resets across all inference-time caches,
ensuring consistent state transitions during startup and reload.
"""

from __future__ import annotations

from typing import Protocol


class RuntimeCache(Protocol):
    """Protocol for inference-time caches that need coordinated reset.

    Implementations must support atomic clearing of all cached state,
    reverting to "pre-inference" state without side effects on other modules.
    """

    def clear(self) -> None:
        """Reset all cached state. Called on startup and reload."""
        ...


class CacheManager:
    """Manages atomic reset of all inference-time caches.

    Ensures that cache resets happen in a consistent order, preventing
    state inconsistency if one cache's clear() depends on another.

    Example:
        manager = CacheManager([model_registry, historical_prediction_stage])
        manager.reset_all()  # Atomic reset of both
    """

    def __init__(self, caches: list[RuntimeCache]) -> None:
        """Initialize manager with caches in reset order.

        Args:
            caches: List of RuntimeCache implementations to manage.
                    Order matters: reset happens in this order.
        """
        self.caches = list(caches)

    def reset_all(self) -> None:
        """Atomically reset all managed caches in registration order.

        Each cache.clear() is called in sequence. If any clear() raises,
        the exception propagates and subsequent caches are not reset.

        This ensures that if initialization fails partway, the caches are
        in a known state (either all reset or consistently half-reset).
        """
        for cache in self.caches:
            cache.clear()

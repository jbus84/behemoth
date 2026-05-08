"""Read-only runtime state query interfaces (deprecated: use state_readers instead).

This module is maintained for backward compatibility only.
New code should import directly from src.behemoth.runtime.state_readers.

The protocols have been consolidated into state_readers.py with clearer
method names and behavioral contracts.
"""

from __future__ import annotations

# Forward imports from state_readers for backward compatibility
from src.behemoth.runtime.state_readers import (
    AccountRiskStateReader,
    BarStateReader,
    RuntimeStateReader,
)

__all__ = [
    "BarStateReader",
    "AccountRiskStateReader",
    "RuntimeStateReader",
]

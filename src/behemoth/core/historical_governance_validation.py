"""Compatibility API for month-scoped historical governance validation."""
from __future__ import annotations

from pathlib import Path

from src.behemoth.core.governance_validator import (
    Check,
    GovernanceValidator,
    failed_checks,
    summarize_failures,
)

HistoricalGovernanceCheck = Check

__all__ = [
    "HistoricalGovernanceCheck",
    "failed_checks",
    "summarize_failures",
    "validate_historical_governance",
]


def validate_historical_governance(
    history_dir: Path | str,
    *,
    required_symbols: list[str] | None = None,
    required_months: list[str] | None = None,
) -> list[Check]:
    """Validate historical governance locks and index consistency."""
    validator = GovernanceValidator()
    return validator.validate(
        history_dir,
        required_symbols=required_symbols,
        required_months=required_months,
    )

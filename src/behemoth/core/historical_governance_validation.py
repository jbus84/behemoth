"""Validation helpers for month-scoped historical governance locks.

Public API for historical governance validation. Delegates to GovernanceValidator
for decoupled, testable validation logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.behemoth.core.governance_validator import GovernanceValidator, Check as _Check


@dataclass(frozen=True)
class HistoricalGovernanceCheck:
    """Historical governance validation check result (backwards-compatible alias)."""
    name: str
    ok: bool
    detail: str
    symbol: str = ""
    month: str = ""
    lock_path: str = ""


def failed_checks(checks: list[HistoricalGovernanceCheck]) -> list[HistoricalGovernanceCheck]:
    """Return only failed checks."""
    return [c for c in checks if not bool(c.ok)]


def summarize_failures(checks: list[HistoricalGovernanceCheck], limit: int = 12) -> str:
    """Summarize failures as pipe-delimited string."""
    bad = failed_checks(checks)
    if not bad:
        return ""
    head = bad[: max(1, int(limit))]
    chunks = [
        (
            f"{c.name}"
            + (f" [{c.symbol} {c.month}]" if c.symbol or c.month else "")
            + f": {c.detail}"
        )
        for c in head
    ]
    if len(bad) > len(head):
        chunks.append(f"... and {len(bad) - len(head)} more failures")
    return " | ".join(chunks)


def validate_historical_governance(
    history_dir: Path | str,
    *,
    required_symbols: list[str] | None = None,
    required_months: list[str] | None = None,
) -> list[HistoricalGovernanceCheck]:
    """Validate historical governance locks and index consistency.

    Runs all validation rules via GovernanceValidator and returns results
    as HistoricalGovernanceCheck for API compatibility.
    """
    validator = GovernanceValidator()
    checks_internal = validator.validate(
        history_dir,
        required_symbols=required_symbols,
        required_months=required_months,
    )
    return [_convert_check(c) for c in checks_internal]


def _convert_check(internal_check: _Check) -> HistoricalGovernanceCheck:
    """Convert internal Check to public HistoricalGovernanceCheck."""
    return HistoricalGovernanceCheck(
        name=internal_check.name,
        ok=internal_check.ok,
        detail=internal_check.detail,
        symbol=internal_check.symbol,
        month=internal_check.month,
        lock_path=internal_check.lock_path,
    )

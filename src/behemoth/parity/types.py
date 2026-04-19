"""Shared types for the parity audit harness."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class CheckContext:
    run_id: str
    model_month: str
    reconcile_dir: Path | None
    live_state_db_path: Path | None
    governance_lock_dir: Path | None


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    severity: Severity
    observed: str
    expected: str
    evidence: str

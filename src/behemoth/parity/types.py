"""Shared types for the parity audit harness."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Severity = Literal["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class CheckContext:
    run_id: str = ""
    model_month: str = ""
    reconcile_dir: Path | None = None
    live_state_db_path: Path | None = None
    governance_lock_dir: Path | None = None
    history_dir: Path | None = None
    active_model_months: dict[str, str] = field(default_factory=dict)
    symbols: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    severity: Severity = "critical"
    observed: str = ""
    expected: str = ""
    evidence: str = ""
    surface_id: str = ""
    failures: list[dict] = field(default_factory=list)

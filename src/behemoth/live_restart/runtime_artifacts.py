"""Registry of files written into the live runtime directory.

The ``data/analysis/backtest_reconcile/runtime/`` directory is shared between
the Python API process and the Java JForex runner. Both sides write distinct
files into it, with implicit coupling — a typo'd filename on either side
silently breaks consumers of the cross-process bridge (e.g. PR #139's
restart_verdict propagation only worked because both sides agreed on
``live_restart_reconciliation.json``; if either side renamed it, the
readiness JSON would silently drop the field).

This module names every file the live runtime expects, who owns each, and
what it carries. Consumers that resolve artifact paths should import from
here rather than hardcoding filenames so a rename surfaces as a single
edit instead of a mystery integration bug.

The Java side has its own constants today (e.g. in ``LiveReadinessCoordinator``)
and reads ``live_restart_reconciliation.json`` via
``RestartReconciliation.resolverForRuntimeDir``. A parallel Java registry is a
follow-up; this PR pins the Python side first.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ArtifactOwner = Literal["python", "java"]


@dataclass(frozen=True)
class RuntimeArtifact:
    """A single file written into the live runtime directory.

    - ``key`` is the stable identifier callers use to look up the path.
    - ``filename`` is what's on disk inside ``runtime_dir``.
    - ``owner`` identifies which process is responsible for *writing* the file.
      Other processes may read it.
    - ``description`` is a short human note for operators.
    """

    key: str
    filename: str
    owner: ArtifactOwner
    description: str


# All files the live runtime expects. Adding a new file means adding here.
RUNTIME_ARTIFACTS: tuple[RuntimeArtifact, ...] = (
    RuntimeArtifact(
        key="live_state_db",
        filename="live_state.db",
        owner="python",
        description="Primary DuckDB state — tick_bars, audit_logs, reservations, etc.",
    ),
    RuntimeArtifact(
        key="active_oco_state",
        filename="active_oco_state.json",
        owner="python",
        description="Snapshot of currently-active OCO orders for restart reconciliation.",
    ),
    RuntimeArtifact(
        key="live_runtime_session",
        filename="live_runtime_session.json",
        owner="python",
        description="Persisted session metadata (git, model_month, lock_fingerprint).",
    ),
    RuntimeArtifact(
        key="live_restart_reconciliation",
        filename="live_restart_reconciliation.json",
        owner="python",
        description="Restart reconciliation report (verdict, reasons, eligibility). Read by Java's LiveReadinessStatusWriter.",
    ),
    RuntimeArtifact(
        key="live_broker_snapshot",
        filename="live_broker_snapshot.json",
        owner="java",
        description="Snapshot of broker-side open orders captured by JForexBrokerSnapshotRunner.",
    ),
    RuntimeArtifact(
        key="live_symbol_readiness",
        filename="live_symbol_readiness.json",
        owner="java",
        description="Per-symbol readiness + restart_verdict. Operator-facing readiness signal.",
    ),
    RuntimeArtifact(
        key="live_position_summary",
        filename="live_position_summary.json",
        owner="python",
        description="Periodic summary of open trade positions for the dashboard.",
    ),
)


_BY_KEY: dict[str, RuntimeArtifact] = {a.key: a for a in RUNTIME_ARTIFACTS}


def artifact(key: str) -> RuntimeArtifact:
    """Look up a registered artifact by stable key. Raises KeyError on typos."""
    if key not in _BY_KEY:
        raise KeyError(f"unknown runtime artifact key: {key!r}. Known: {sorted(_BY_KEY)}")
    return _BY_KEY[key]


def artifact_path(key: str, runtime_dir: Path) -> Path:
    """Return the canonical path for a registered artifact under ``runtime_dir``."""
    return runtime_dir / artifact(key).filename


def all_artifacts() -> tuple[RuntimeArtifact, ...]:
    """All registered artifacts, in declaration order."""
    return RUNTIME_ARTIFACTS

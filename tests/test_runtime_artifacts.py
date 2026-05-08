"""Tests for the runtime artifact registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.behemoth.live_restart.runtime_artifacts import (
    RUNTIME_ARTIFACTS,
    RuntimeArtifact,
    all_artifacts,
    artifact,
    artifact_path,
)


def test_keys_are_unique() -> None:
    keys = [a.key for a in RUNTIME_ARTIFACTS]
    assert len(keys) == len(set(keys)), f"duplicate keys: {keys}"


def test_filenames_are_unique() -> None:
    filenames = [a.filename for a in RUNTIME_ARTIFACTS]
    assert len(filenames) == len(set(filenames)), f"duplicate filenames: {filenames}"


def test_artifact_lookup_by_key_returns_record() -> None:
    rec = artifact("live_state_db")
    assert isinstance(rec, RuntimeArtifact)
    assert rec.filename == "live_state.db"
    assert rec.owner == "python"


def test_unknown_key_raises_with_helpful_message() -> None:
    with pytest.raises(KeyError, match="unknown runtime artifact key"):
        artifact("does_not_exist")


def test_artifact_path_joins_runtime_dir() -> None:
    runtime_dir = Path("/tmp/runtime")
    path = artifact_path("live_restart_reconciliation", runtime_dir)
    assert path == runtime_dir / "live_restart_reconciliation.json"


def test_each_artifact_has_owner_python_or_java() -> None:
    for rec in all_artifacts():
        assert rec.owner in ("python", "java"), f"{rec.key}: invalid owner {rec.owner!r}"


def test_each_artifact_has_nonempty_description() -> None:
    for rec in all_artifacts():
        assert rec.description.strip(), f"{rec.key}: empty description"


def test_known_artifacts_match_canonical_set() -> None:
    """Pin the set so accidental adds/removes are caught in review."""
    expected = {
        "live_state_db",
        "active_oco_state",
        "live_runtime_session",
        "live_restart_reconciliation",
        "live_broker_snapshot",
        "live_symbol_readiness",
        "live_position_summary",
    }
    actual = {a.key for a in RUNTIME_ARTIFACTS}
    assert actual == expected, (
        f"unexpected runtime artifact set. extra: {actual - expected}, "
        f"missing: {expected - actual}"
    )

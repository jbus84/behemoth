from __future__ import annotations

import json
from pathlib import Path

from src.behemoth.live_restart.reconciliation import (
    ReconciliationReport,
    RestartVerdict,
    RuntimeFileSnapshot,
    RuntimeSessionMetadata,
    compare_runtime_context,
    compute_lock_fingerprint,
    load_promoted_model_month,
    load_runtime_session_metadata,
    write_reconciliation_report,
    write_runtime_session_metadata,
)


def test_compute_lock_fingerprint_is_stable_for_same_files(tmp_path: Path) -> None:
    governance_dir = tmp_path / "oco"
    governance_dir.mkdir()
    (governance_dir / "eurusd_oco_allowed_states.csv").write_text(
        "symbol,state_id\nEURUSD,s1\n",
        encoding="utf-8",
    )
    (governance_dir / "eurusd_oco_live_lock.json").write_text(
        '{"symbol":"EURUSD"}\n',
        encoding="utf-8",
    )

    first = compute_lock_fingerprint(governance_dir)
    second = compute_lock_fingerprint(governance_dir)

    assert first == second


def test_compare_runtime_context_returns_incompatible_on_lock_fingerprint_mismatch() -> None:
    persisted = RuntimeSessionMetadata(
        git_commit="abc",
        git_branch="main",
        git_dirty=False,
        repo_root="/repo",
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="old",
        symbols=["EURUSD", "GBPUSD"],
        started_at_utc="2026-04-22T00:00:00Z",
        startup_mode="resume",
    )
    current = RuntimeSessionMetadata(
        git_commit="abc",
        git_branch="main",
        git_dirty=False,
        repo_root="/repo",
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="new",
        symbols=["EURUSD", "GBPUSD"],
        started_at_utc="2026-04-22T00:10:00Z",
        startup_mode="resume",
    )

    result = compare_runtime_context(persisted, current)

    assert result.verdict is RestartVerdict.INCOMPATIBLE
    assert any("lock_fingerprint" in reason for reason in result.reasons)


def test_compare_runtime_context_blocks_live_sensitive_git_dirty() -> None:
    persisted = RuntimeSessionMetadata(
        git_commit="abc",
        git_branch="main",
        git_dirty=False,
        repo_root="/repo",
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="fp",
        symbols=["EURUSD", "GBPUSD"],
        started_at_utc="2026-04-22T00:00:00Z",
        startup_mode="resume",
    )
    current = RuntimeSessionMetadata(
        git_commit="abc",
        git_branch="main",
        git_dirty=True,
        repo_root="/repo",
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="fp",
        symbols=["EURUSD", "GBPUSD"],
        started_at_utc="2026-04-22T00:10:00Z",
        startup_mode="resume",
    )

    result = compare_runtime_context(persisted, current)

    assert result.verdict is RestartVerdict.INCOMPATIBLE
    assert "git_dirty workspace" in result.reasons


def test_load_promoted_model_month_reads_live_lock_artifacts(tmp_path: Path) -> None:
    governance_dir = tmp_path / "oco"
    governance_dir.mkdir()
    (governance_dir / "eurusd_oco_live_lock.json").write_text(
        json.dumps(
            {
                "symbol": "EURUSD",
                "artifacts": {
                    "live_deployable": True,
                    "model_month": "2026-03",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (governance_dir / "audusd_oco_live_lock.json").write_text(
        json.dumps(
            {
                "symbol": "AUDUSD",
                "artifacts": {
                    "live_deployable": False,
                    "model_month": "2026-04",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert load_promoted_model_month(governance_dir) == "2026-03"


def test_compare_runtime_context_blocks_orphaned_runtime_state_without_metadata() -> None:
    current = RuntimeSessionMetadata(
        git_commit="abc",
        git_branch="main",
        git_dirty=False,
        repo_root="/repo",
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="fp",
        symbols=["EURUSD", "GBPUSD"],
        started_at_utc="2026-04-22T00:10:00Z",
        startup_mode="resume",
    )
    local_state = RuntimeFileSnapshot(
        runtime_dir="/repo/data/analysis/backtest_reconcile/runtime",
        live_state_db_path="/repo/data/analysis/backtest_reconcile/runtime/live_state.db",
        active_oco_state_path="/repo/data/analysis/backtest_reconcile/runtime/active_oco_state.json",
        runtime_session_path="/repo/data/analysis/backtest_reconcile/runtime/live_runtime_session.json",
        live_state_exists=True,
        live_state_readable=True,
        active_oco_state_exists=True,
        active_oco_state_parsed=True,
        runtime_session_exists=False,
        runtime_session_parsed=False,
    )

    result = compare_runtime_context(None, current, local_state=local_state)

    assert result.verdict is RestartVerdict.INCOMPATIBLE
    assert "persisted runtime session metadata missing" in result.reasons


def test_compare_runtime_context_blocks_commit_drift() -> None:
    persisted = RuntimeSessionMetadata(
        git_commit="abc",
        git_branch="main",
        git_dirty=False,
        repo_root="/repo",
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="fp",
        symbols=["EURUSD", "GBPUSD"],
        started_at_utc="2026-04-22T00:00:00Z",
        startup_mode="resume",
    )
    current = RuntimeSessionMetadata(
        git_commit="def",
        git_branch="main",
        git_dirty=False,
        repo_root="/repo",
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="fp",
        symbols=["EURUSD", "GBPUSD"],
        started_at_utc="2026-04-22T00:10:00Z",
        startup_mode="resume",
    )

    result = compare_runtime_context(persisted, current)

    assert result.verdict is RestartVerdict.INCOMPATIBLE
    assert "git_commit changed" in result.reasons


def test_runtime_session_metadata_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "live_runtime_session.json"
    meta = RuntimeSessionMetadata(
        git_commit="abc",
        git_branch="main",
        git_dirty=False,
        repo_root="/repo",
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="fp",
        symbols=["EURUSD"],
        started_at_utc="2026-04-22T00:00:00Z",
        startup_mode="resume",
    )

    write_runtime_session_metadata(path, meta)
    loaded = load_runtime_session_metadata(path)

    assert loaded == meta


def test_write_reconciliation_report_writes_expected_verdict(tmp_path: Path) -> None:
    path = tmp_path / "live_restart_reconciliation.json"
    report = ReconciliationReport(
        startup_mode="resume",
        verdict=RestartVerdict.CLEAN_RESUMABLE,
        reasons=[],
        repaired_items=[],
    )

    write_reconciliation_report(path, report)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["verdict"] == "clean_resumable"
    assert payload["startup_mode"] == "resume"

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from src.behemoth.live_restart.reconciliation import (
    BrokerSnapshot,
    BrokerSnapshotOrder,
    LocalRuntimeStateSummary,
    ReconciliationReport,
    RuntimeContextComparison,
    RuntimeFileSnapshot,
    RuntimeSessionMetadata,
    compare_runtime_context,
    compute_lock_fingerprint,
    inspect_local_runtime_state,
    load_broker_snapshot,
    load_promoted_model_month,
    load_runtime_session_metadata,
    write_reconciliation_report,
    write_runtime_session_metadata,
)
from src.behemoth.ops.verdicts import RestartEligibility


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

    assert result.verdict is RestartEligibility.RESTART_BLOCKED
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

    assert result.verdict is RestartEligibility.RESTART_BLOCKED
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

    assert result.verdict is RestartEligibility.RESTART_BLOCKED
    assert "persisted runtime session metadata missing" in result.reasons


def test_load_broker_snapshot_round_trips_orders(tmp_path: Path) -> None:
    path = tmp_path / "live_broker_snapshot.json"
    path.write_text(
        json.dumps(
            {
                "captured_at_utc": "2026-04-22T12:00:00Z",
                "orders": [
                    {
                        "order_id": "abc-1",
                        "label": "EURUSD_BUY_1",
                        "symbol": "EURUSD",
                        "state": "FILLED",
                        "order_command": "BUY",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = load_broker_snapshot(path)

    assert snapshot == BrokerSnapshot(
        captured_at_utc="2026-04-22T12:00:00Z",
        orders=[
            BrokerSnapshotOrder(
                order_id="abc-1",
                label="EURUSD_BUY_1",
                symbol="EURUSD",
                state="FILLED",
                order_command="BUY",
            )
        ],
    )


def test_inspect_local_runtime_state_tracks_symbols_and_broker_links(tmp_path: Path) -> None:
    state_db = tmp_path / "live_state.db"
    con = duckdb.connect(str(state_db))
    try:
        con.execute(
            """
            CREATE TABLE account_risk_reservations (
                reservation_id VARCHAR,
                created_ts TIMESTAMPTZ,
                symbol VARCHAR,
                broker_pos_id VARCHAR,
                status VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE barrier_scans (
                scan_id VARCHAR,
                created_ts TIMESTAMPTZ,
                symbol VARCHAR,
                broker_pos_id VARCHAR,
                status VARCHAR
            )
            """
        )
        con.execute(
            """
            INSERT INTO account_risk_reservations VALUES
            ('res-pending', TIMESTAMPTZ '2026-04-22T00:00:00Z', 'EURUSD', NULL, 'PENDING'),
            ('res-open', TIMESTAMPTZ '2026-04-22T00:01:00Z', 'GBPUSD', 'broker-1', 'OPEN')
            """
        )
        con.execute(
            """
            INSERT INTO barrier_scans VALUES
            ('scan-pending', TIMESTAMPTZ '2026-04-22T00:02:00Z', 'EURUSD', NULL, 'SCANNING'),
            ('scan-holding', TIMESTAMPTZ '2026-04-22T00:03:00Z', 'USDJPY', 'broker-2', 'HOLDING')
            """
        )
    finally:
        con.close()

    summary = inspect_local_runtime_state(state_db)

    assert summary == LocalRuntimeStateSummary(
        active_reservation_count=2,
        active_scan_count=2,
        active_reservation_ids=["res-pending", "res-open"],
        active_scan_ids=["scan-pending", "scan-holding"],
        active_symbols=["EURUSD", "GBPUSD", "USDJPY"],
        broker_link_symbols=["GBPUSD", "USDJPY"],
        linked_broker_position_ids=["broker-1", "broker-2"],
    )


def test_compare_runtime_context_blocks_when_broker_has_open_orders_but_local_state_is_empty() -> None:
    persisted = RuntimeSessionMetadata(
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
    current = RuntimeSessionMetadata(
        git_commit="abc",
        git_branch="main",
        git_dirty=False,
        repo_root="/repo",
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="fp",
        symbols=["EURUSD"],
        started_at_utc="2026-04-22T00:10:00Z",
        startup_mode="resume",
    )
    local_state = RuntimeFileSnapshot(
        runtime_dir="/repo/runtime",
        live_state_db_path="/repo/runtime/live_state.db",
        active_oco_state_path="/repo/runtime/active_oco_state.json",
        runtime_session_path="/repo/runtime/live_runtime_session.json",
        live_state_exists=True,
        live_state_readable=True,
        active_oco_state_exists=False,
        active_oco_state_parsed=False,
        runtime_session_exists=True,
        runtime_session_parsed=True,
    )
    broker_snapshot = BrokerSnapshot(
        captured_at_utc="2026-04-22T12:00:00Z",
        orders=[
            BrokerSnapshotOrder(
                order_id="abc-1",
                label="EURUSD_BUY_1",
                symbol="EURUSD",
                state="FILLED",
                order_command="BUY",
            )
        ],
    )
    local_runtime = LocalRuntimeStateSummary(
        active_reservation_count=0,
        active_scan_count=0,
        active_reservation_ids=[],
        active_scan_ids=[],
    )

    result = compare_runtime_context(
        persisted,
        current,
        local_state=local_state,
        broker_snapshot=broker_snapshot,
        local_runtime=local_runtime,
    )

    assert result.verdict is RestartEligibility.RESTART_BLOCKED
    assert "broker snapshot has open orders but local runtime has no active state" in result.reasons


def test_compare_runtime_context_blocks_when_local_state_is_active_but_broker_is_empty() -> None:
    persisted = RuntimeSessionMetadata(
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
    current = RuntimeSessionMetadata(
        git_commit="abc",
        git_branch="main",
        git_dirty=False,
        repo_root="/repo",
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="fp",
        symbols=["EURUSD"],
        started_at_utc="2026-04-22T00:10:00Z",
        startup_mode="resume",
    )
    local_state = RuntimeFileSnapshot(
        runtime_dir="/repo/runtime",
        live_state_db_path="/repo/runtime/live_state.db",
        active_oco_state_path="/repo/runtime/active_oco_state.json",
        runtime_session_path="/repo/runtime/live_runtime_session.json",
        live_state_exists=True,
        live_state_readable=True,
        active_oco_state_exists=True,
        active_oco_state_parsed=True,
        runtime_session_exists=True,
        runtime_session_parsed=True,
    )
    local_runtime = LocalRuntimeStateSummary(
        active_reservation_count=1,
        active_scan_count=0,
        active_reservation_ids=["res-1"],
        active_scan_ids=[],
    )

    result = compare_runtime_context(
        persisted,
        current,
        local_state=local_state,
        broker_snapshot=BrokerSnapshot(captured_at_utc="2026-04-22T12:00:00Z", orders=[]),
        local_runtime=local_runtime,
    )

    assert result.verdict is RestartEligibility.RESTART_BLOCKED
    assert "local runtime has active state but broker snapshot is empty" in result.reasons


def test_compare_runtime_context_blocks_symbol_level_broker_link_mismatch() -> None:
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
        runtime_dir="/repo/runtime",
        live_state_db_path="/repo/runtime/live_state.db",
        active_oco_state_path="/repo/runtime/active_oco_state.json",
        runtime_session_path="/repo/runtime/live_runtime_session.json",
        live_state_exists=True,
        live_state_readable=True,
        active_oco_state_exists=True,
        active_oco_state_parsed=True,
        runtime_session_exists=True,
        runtime_session_parsed=True,
    )
    local_runtime = LocalRuntimeStateSummary(
        active_reservation_count=1,
        active_scan_count=0,
        active_reservation_ids=["res-1"],
        active_scan_ids=[],
        active_symbols=["EURUSD"],
        broker_link_symbols=["EURUSD"],
        linked_broker_position_ids=["broker-1"],
    )
    broker_snapshot = BrokerSnapshot(
        captured_at_utc="2026-04-22T12:00:00Z",
        orders=[
            BrokerSnapshotOrder(
                order_id="broker-1",
                label="GBPUSD_BUY_1",
                symbol="GBPUSD",
                state="FILLED",
                order_command="BUY",
            )
        ],
    )

    result = compare_runtime_context(
        persisted,
        current,
        local_state=local_state,
        broker_snapshot=broker_snapshot,
        local_runtime=local_runtime,
    )

    assert result.verdict is RestartEligibility.RESTART_BLOCKED
    assert "broker-linked symbols do not match broker snapshot symbols" in result.reasons


def test_compare_runtime_context_blocks_broker_position_id_mismatch() -> None:
    persisted = RuntimeSessionMetadata(
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
    current = RuntimeSessionMetadata(
        git_commit="abc",
        git_branch="main",
        git_dirty=False,
        repo_root="/repo",
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="fp",
        symbols=["EURUSD"],
        started_at_utc="2026-04-22T00:10:00Z",
        startup_mode="resume",
    )
    local_state = RuntimeFileSnapshot(
        runtime_dir="/repo/runtime",
        live_state_db_path="/repo/runtime/live_state.db",
        active_oco_state_path="/repo/runtime/active_oco_state.json",
        runtime_session_path="/repo/runtime/live_runtime_session.json",
        live_state_exists=True,
        live_state_readable=True,
        active_oco_state_exists=True,
        active_oco_state_parsed=True,
        runtime_session_exists=True,
        runtime_session_parsed=True,
    )
    local_runtime = LocalRuntimeStateSummary(
        active_reservation_count=1,
        active_scan_count=0,
        active_reservation_ids=["res-1"],
        active_scan_ids=[],
        active_symbols=["EURUSD"],
        broker_link_symbols=["EURUSD"],
        linked_broker_position_ids=["broker-1"],
    )

    result = compare_runtime_context(
        persisted,
        current,
        local_state=local_state,
        broker_snapshot=BrokerSnapshot(
            captured_at_utc="2026-04-22T12:00:00Z",
            orders=[
                BrokerSnapshotOrder(
                    order_id="broker-9",
                    label="EURUSD_BUY_1",
                    symbol="EURUSD",
                    state="FILLED",
                    order_command="BUY",
                )
            ],
        ),
        local_runtime=local_runtime,
    )

    assert result.verdict is RestartEligibility.RESTART_BLOCKED
    assert "broker-linked position ids do not match broker snapshot order ids" in result.reasons


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

    assert result.verdict is RestartEligibility.RESTART_BLOCKED
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
        verdict=RestartEligibility.RESTART_ELIGIBLE,
        reasons=[],
        repaired_items=[],
    )

    write_reconciliation_report(path, report)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["verdict"] == "RESTART_ELIGIBLE"
    assert payload["startup_mode"] == "resume"


def test_derive_restart_eligibility_maps_clean_resume_to_eligible() -> None:
    from src.behemoth.live_restart.reconciliation import derive_restart_eligibility

    result = derive_restart_eligibility(
        RuntimeContextComparison(verdict=RestartEligibility.RESTART_ELIGIBLE, reasons=[])
    )

    assert result.eligibility is RestartEligibility.RESTART_ELIGIBLE
    assert result.allow_new_entries is True


def test_derive_restart_eligibility_maps_reconcilable_to_drain_only() -> None:
    from src.behemoth.live_restart.reconciliation import derive_restart_eligibility

    result = derive_restart_eligibility(
        RuntimeContextComparison(
            verdict=RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY,
            reasons=["local runtime has recoverable active state"],
        )
    )

    assert result.eligibility is RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY
    assert result.allow_new_entries is False
    assert result.reasons == ["local runtime has recoverable active state"]


def test_derive_restart_eligibility_maps_incompatible_to_blocked() -> None:
    from src.behemoth.live_restart.reconciliation import derive_restart_eligibility

    result = derive_restart_eligibility(
        RuntimeContextComparison(
            verdict=RestartEligibility.RESTART_BLOCKED,
            reasons=["lock_fingerprint mismatch"],
        )
    )

    assert result.eligibility is RestartEligibility.RESTART_BLOCKED
    assert result.allow_new_entries is False


# ---------------------------------------------------------------------------
# ReconciliationCycle
# ---------------------------------------------------------------------------


def _make_metadata(**overrides):
    from src.behemoth.live_restart.reconciliation import RuntimeSessionMetadata

    base = dict(
        git_commit="commit-abc",
        git_branch="main",
        git_dirty=False,
        repo_root="/repo",
        model_month="2026-04",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="fp-1",
        symbols=["EURUSD"],
        started_at_utc="2026-05-08T10:00:00Z",
        startup_mode="reset",
    )
    base.update(overrides)
    return RuntimeSessionMetadata(**base)


def test_cycle_finalize_writes_report_and_persisted_metadata(tmp_path) -> None:
    from src.behemoth.live_restart.reconciliation import (
        ReconciliationCycle,
        load_runtime_session_metadata,
    )

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cycle = ReconciliationCycle(
        runtime_dir=runtime,
        state_db_path=runtime / "state.db",
        active_state_path=runtime / "active.json",
        session_metadata_path=runtime / "session.json",
        reconciliation_report_path=runtime / "report.json",
        broker_snapshot_path=runtime / "broker.json",
        startup_mode="reset",
        build_current_metadata=_make_metadata,
        load_promoted_symbols=lambda: ["EURUSD"],
    )
    cycle.snapshot()
    cycle.finalize()

    assert (runtime / "report.json").exists()
    assert (runtime / "session.json").exists()
    persisted = load_runtime_session_metadata(runtime / "session.json")
    assert persisted is not None
    assert persisted.git_commit == "commit-abc"


def test_cycle_invalidate_after_mutation_re_snapshots_with_clean_state(tmp_path) -> None:
    """Reset cleanup wipes local files; cycle must reflect post-cleanup state
    in the finalized report — not the pre-cleanup snapshot."""
    import json

    from src.behemoth.live_restart.reconciliation import ReconciliationCycle
    from src.behemoth.ops.verdicts import RestartEligibility

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    state_db = runtime / "state.db"
    active = runtime / "active.json"
    session = runtime / "session.json"
    # Pre-existing stale state — would normally trigger RESTART_BLOCKED
    state_db.write_bytes(b"")
    active.write_text("{}")
    # Stale persisted with mismatched git
    stale = _make_metadata(git_commit="STALE", startup_mode="resume")
    from src.behemoth.live_restart.reconciliation import write_runtime_session_metadata
    write_runtime_session_metadata(session, stale)

    cycle = ReconciliationCycle(
        runtime_dir=runtime,
        state_db_path=state_db,
        active_state_path=active,
        session_metadata_path=session,
        reconciliation_report_path=runtime / "report.json",
        broker_snapshot_path=runtime / "broker.json",
        startup_mode="reset",
        build_current_metadata=lambda: _make_metadata(git_commit="CURRENT"),
        load_promoted_symbols=lambda: ["EURUSD"],
    )
    cycle.snapshot()
    # Initial snapshot should be RESTART_BLOCKED (git_commit changed)
    assert cycle.current.comparison.verdict is RestartEligibility.RESTART_BLOCKED

    # Simulate reset cleanup: wipe local state files
    state_db.unlink()
    active.unlink()
    cycle.invalidate_after_mutation()

    # Post-cleanup snapshot: persisted=None (cycle wiped it), local state empty
    assert cycle.current.persisted_metadata is None
    assert cycle.current.comparison.verdict is RestartEligibility.RESTART_ELIGIBLE
    assert cycle.current.comparison.reasons == []

    cycle.finalize()
    # Finalized report reflects the POST-mutation snapshot, not the pre-mutation one
    report = json.loads((runtime / "report.json").read_text())
    assert report["verdict"] == "RESTART_ELIGIBLE"
    assert report["reasons"] == []


def test_cycle_finalize_is_terminal(tmp_path) -> None:
    import pytest

    from src.behemoth.live_restart.reconciliation import ReconciliationCycle

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    cycle = ReconciliationCycle(
        runtime_dir=runtime,
        state_db_path=runtime / "state.db",
        active_state_path=runtime / "active.json",
        session_metadata_path=runtime / "session.json",
        reconciliation_report_path=runtime / "report.json",
        broker_snapshot_path=runtime / "broker.json",
        startup_mode="reset",
        build_current_metadata=_make_metadata,
        load_promoted_symbols=lambda: ["EURUSD"],
    )
    cycle.finalize()
    with pytest.raises(RuntimeError, match="finalize called twice"):
        cycle.finalize()
    with pytest.raises(RuntimeError, match="cannot invalidate a finalized"):
        cycle.invalidate_after_mutation()

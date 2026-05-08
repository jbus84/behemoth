from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

import duckdb

from src.behemoth.ops.verdicts import RestartEligibility


@dataclass(frozen=True)
class RuntimeSessionMetadata:
    git_commit: str
    git_branch: str
    git_dirty: bool
    repo_root: str
    model_month: str
    governance_dir: str
    lock_fingerprint: str
    symbols: list[str]
    started_at_utc: str
    startup_mode: str


@dataclass(frozen=True)
class RuntimeFileSnapshot:
    runtime_dir: str
    live_state_db_path: str
    active_oco_state_path: str
    runtime_session_path: str
    live_state_exists: bool
    live_state_readable: bool
    active_oco_state_exists: bool
    active_oco_state_parsed: bool
    runtime_session_exists: bool
    runtime_session_parsed: bool


@dataclass(frozen=True)
class BrokerSnapshotOrder:
    order_id: str
    label: str
    symbol: str
    state: str
    order_command: str


@dataclass(frozen=True)
class BrokerSnapshot:
    captured_at_utc: str
    orders: list[BrokerSnapshotOrder] = field(default_factory=list)

    def has_active_orders(self) -> bool:
        terminal_states = {"CANCELED", "CLOSED"}
        return any(order.state.upper() not in terminal_states for order in self.orders)

    def active_symbols(self) -> list[str]:
        terminal_states = {"CANCELED", "CLOSED"}
        return sorted(
            {
                order.symbol.upper()
                for order in self.orders
                if order.state.upper() not in terminal_states and order.symbol.strip()
            }
        )

    def active_order_ids(self) -> list[str]:
        terminal_states = {"CANCELED", "CLOSED"}
        return sorted(
            {
                order.order_id
                for order in self.orders
                if order.state.upper() not in terminal_states and order.order_id.strip()
            }
        )


@dataclass(frozen=True)
class LocalRuntimeStateSummary:
    active_reservation_count: int
    active_scan_count: int
    active_reservation_ids: list[str] = field(default_factory=list)
    active_scan_ids: list[str] = field(default_factory=list)
    active_symbols: list[str] = field(default_factory=list)
    broker_link_symbols: list[str] = field(default_factory=list)
    linked_broker_position_ids: list[str] = field(default_factory=list)

    def has_active_state(self) -> bool:
        return self.active_reservation_count > 0 or self.active_scan_count > 0

    def has_broker_linked_state(self) -> bool:
        return bool(self.broker_link_symbols or self.linked_broker_position_ids)


@dataclass(frozen=True)
class RuntimeContextComparison:
    verdict: RestartEligibility
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RestartEligibilityResult:
    eligibility: RestartEligibility
    allow_new_entries: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReconciliationReport:
    startup_mode: str
    verdict: RestartEligibility
    reasons: list[str]
    repaired_items: list[str]
    current: RuntimeSessionMetadata | None = None
    persisted: RuntimeSessionMetadata | None = None
    local_state: RuntimeFileSnapshot | None = None
    local_runtime: LocalRuntimeStateSummary | None = None
    broker_snapshot: BrokerSnapshot | None = None
    promoted_symbols: list[str] = field(default_factory=list)
    restart_eligibility: RestartEligibilityResult | None = None


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(val) for key, val in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _runtime_digest():
    return sha256()


def _iter_promoted_lock_payloads(governance_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not governance_dir.exists():
        return []
    payloads: list[tuple[Path, dict[str, Any]]] = []
    for lock_path in sorted(governance_dir.glob("*_oco_live_lock.json")):
        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        artifacts = data.get("artifacts", {})
        if isinstance(artifacts, dict) and bool(artifacts.get("live_deployable", True)) is False:
            continue
        payloads.append((lock_path, data))
    return payloads


def compute_lock_fingerprint(governance_dir: Path) -> str:
    if not governance_dir.exists():
        raise FileNotFoundError(f"Governance directory not found: {governance_dir}")
    if not governance_dir.is_dir():
        raise NotADirectoryError(f"Governance path is not a directory: {governance_dir}")

    digest = _runtime_digest()
    candidate_paths: list[Path] = []
    for lock_path, payload in _iter_promoted_lock_payloads(governance_dir):
        candidate_paths.append(lock_path)
        symbol = str(payload.get("symbol", "")).strip().lower()
        if symbol:
            allowed_states_path = governance_dir / f"{symbol}_oco_allowed_states.csv"
            if allowed_states_path.is_file():
                candidate_paths.append(allowed_states_path)
    for path in sorted(set(candidate_paths), key=lambda item: item.relative_to(governance_dir).as_posix()):
        digest.update(path.relative_to(governance_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_promoted_symbols(governance_dir: Path) -> list[str]:
    symbols: list[str] = []
    for _lock_path, data in _iter_promoted_lock_payloads(governance_dir):
        symbol = str(data.get("symbol", "")).upper().strip()
        if symbol:
            symbols.append(symbol)
    return sorted(set(symbols))


def load_promoted_model_month(governance_dir: Path) -> str | None:
    months: set[str] = set()
    for _lock_path, data in _iter_promoted_lock_payloads(governance_dir):
        artifacts = data.get("artifacts", {})
        if not isinstance(artifacts, dict):
            continue
        model_month = str(artifacts.get("model_month", "")).strip()
        if model_month:
            months.add(model_month)
    if not months:
        return None
    return sorted(months)[-1]


def load_runtime_session_metadata(path: Path) -> RuntimeSessionMetadata:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RuntimeSessionMetadata(
        git_commit=str(payload["git_commit"]),
        git_branch=str(payload["git_branch"]),
        git_dirty=bool(payload["git_dirty"]),
        repo_root=str(payload["repo_root"]),
        model_month=str(payload["model_month"]),
        governance_dir=str(payload["governance_dir"]),
        lock_fingerprint=str(payload["lock_fingerprint"]),
        symbols=[str(sym) for sym in payload.get("symbols", [])],
        started_at_utc=str(payload["started_at_utc"]),
        startup_mode=str(payload["startup_mode"]),
    )


def load_broker_snapshot(path: Path) -> BrokerSnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    orders = [
        BrokerSnapshotOrder(
            order_id=str(item["order_id"]),
            label=str(item["label"]),
            symbol=str(item["symbol"]),
            state=str(item["state"]),
            order_command=str(item["order_command"]),
        )
        for item in payload.get("orders", [])
    ]
    return BrokerSnapshot(
        captured_at_utc=str(payload["captured_at_utc"]),
        orders=orders,
    )


def write_runtime_session_metadata(path: Path, metadata: RuntimeSessionMetadata) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(metadata), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def inspect_runtime_files(
    runtime_dir: Path,
    state_db_path: Path,
    active_state_path: Path,
    session_metadata_path: Path,
) -> RuntimeFileSnapshot:
    live_state_exists = state_db_path.exists()
    live_state_readable = False
    if live_state_exists:
        try:
            con = duckdb.connect(str(state_db_path), read_only=True)
            con.execute("SHOW TABLES").fetchall()
            con.close()
            live_state_readable = True
        except Exception:
            live_state_readable = False

    active_oco_state_exists = active_state_path.exists()
    active_oco_state_parsed = False
    if active_oco_state_exists:
        try:
            json.loads(active_state_path.read_text(encoding="utf-8"))
            active_oco_state_parsed = True
        except Exception:
            active_oco_state_parsed = False

    runtime_session_exists = session_metadata_path.exists()
    runtime_session_parsed = False
    if runtime_session_exists:
        try:
            json.loads(session_metadata_path.read_text(encoding="utf-8"))
            runtime_session_parsed = True
        except Exception:
            runtime_session_parsed = False

    return RuntimeFileSnapshot(
        runtime_dir=str(runtime_dir),
        live_state_db_path=str(state_db_path),
        active_oco_state_path=str(active_state_path),
        runtime_session_path=str(session_metadata_path),
        live_state_exists=live_state_exists,
        live_state_readable=live_state_readable,
        active_oco_state_exists=active_oco_state_exists,
        active_oco_state_parsed=active_oco_state_parsed,
        runtime_session_exists=runtime_session_exists,
        runtime_session_parsed=runtime_session_parsed,
    )


def _table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ? LIMIT 1",
        [table_name],
    ).fetchone()
    return row is not None


def inspect_local_runtime_state(state_db_path: Path) -> LocalRuntimeStateSummary:
    if not state_db_path.exists():
        return LocalRuntimeStateSummary(
            active_reservation_count=0,
            active_scan_count=0,
            active_reservation_ids=[],
            active_scan_ids=[],
            active_symbols=[],
            broker_link_symbols=[],
            linked_broker_position_ids=[],
        )

    con = duckdb.connect(str(state_db_path), read_only=True)
    try:
        active_reservation_ids: list[str] = []
        active_scan_ids: list[str] = []
        active_symbols: set[str] = set()
        broker_link_symbols: set[str] = set()
        linked_broker_position_ids: set[str] = set()

        if _table_exists(con, "account_risk_reservations"):
            reservation_rows = con.execute(
                    """
                    SELECT reservation_id, symbol, broker_pos_id, status
                    FROM account_risk_reservations
                    WHERE status IN ('PENDING', 'OPEN')
                    ORDER BY created_ts ASC
                    """
                ).fetchall()
            active_reservation_ids = [str(row[0]) for row in reservation_rows]
            for _reservation_id, symbol, broker_pos_id, status in reservation_rows:
                symbol_text = str(symbol).upper().strip()
                if symbol_text:
                    active_symbols.add(symbol_text)
                    if str(status).upper() == "OPEN" or broker_pos_id is not None:
                        broker_link_symbols.add(symbol_text)
                if broker_pos_id is not None and str(broker_pos_id).strip():
                    linked_broker_position_ids.add(str(broker_pos_id))

        if _table_exists(con, "barrier_scans"):
            scan_rows = con.execute(
                    """
                    SELECT scan_id, symbol, broker_pos_id, status
                    FROM barrier_scans
                    WHERE status IN ('SCANNING', 'HOLDING')
                    ORDER BY created_ts ASC
                    """
                ).fetchall()
            active_scan_ids = [str(row[0]) for row in scan_rows]
            for _scan_id, symbol, broker_pos_id, status in scan_rows:
                symbol_text = str(symbol).upper().strip()
                if symbol_text:
                    active_symbols.add(symbol_text)
                    if str(status).upper() == "HOLDING" or broker_pos_id is not None:
                        broker_link_symbols.add(symbol_text)
                if broker_pos_id is not None and str(broker_pos_id).strip():
                    linked_broker_position_ids.add(str(broker_pos_id))

        return LocalRuntimeStateSummary(
            active_reservation_count=len(active_reservation_ids),
            active_scan_count=len(active_scan_ids),
            active_reservation_ids=active_reservation_ids,
            active_scan_ids=active_scan_ids,
            active_symbols=sorted(active_symbols),
            broker_link_symbols=sorted(broker_link_symbols),
            linked_broker_position_ids=sorted(linked_broker_position_ids),
        )
    finally:
        con.close()


def compare_runtime_context(
    persisted: RuntimeSessionMetadata | None,
    current: RuntimeSessionMetadata,
    local_state: RuntimeFileSnapshot | None = None,
    broker_snapshot: BrokerSnapshot | None = None,
    local_runtime: LocalRuntimeStateSummary | None = None,
) -> RuntimeContextComparison:
    reasons: list[str] = []
    hard_fail = False

    if persisted is None:
        if local_state is not None:
            if local_state.live_state_exists or local_state.active_oco_state_exists:
                reasons.append("persisted runtime session metadata missing")
                hard_fail = True
            if local_state.runtime_session_exists and not local_state.runtime_session_parsed:
                reasons.append("runtime session metadata unreadable")
                hard_fail = True
            if local_state.live_state_exists and not local_state.live_state_readable:
                reasons.append("live_state.db unreadable")
                hard_fail = True
            if local_state.active_oco_state_exists and not local_state.active_oco_state_parsed:
                reasons.append("active_oco_state.json unreadable")
                hard_fail = True
        return RuntimeContextComparison(
            verdict=RestartEligibility.RESTART_BLOCKED if hard_fail else RestartEligibility.RESTART_ELIGIBLE,
            reasons=reasons,
        )

    if persisted.lock_fingerprint != current.lock_fingerprint:
        reasons.append("lock_fingerprint mismatch")
        hard_fail = True
    if persisted.model_month != current.model_month:
        reasons.append("model_month mismatch")
        hard_fail = True
    if persisted.governance_dir != current.governance_dir:
        reasons.append("governance_dir mismatch")
        hard_fail = True
    if persisted.symbols != current.symbols:
        reasons.append("symbol set mismatch")
        hard_fail = True
    if local_state is not None:
        if local_state.runtime_session_exists and not local_state.runtime_session_parsed:
            reasons.append("runtime session metadata unreadable")
            hard_fail = True
        if not local_state.live_state_exists:
            reasons.append("live_state.db missing")
            hard_fail = True
        elif not local_state.live_state_readable:
            reasons.append("live_state.db unreadable")
            hard_fail = True
        if not local_state.active_oco_state_exists:
            reasons.append("active_oco_state.json missing")
            hard_fail = True
        elif not local_state.active_oco_state_parsed:
            reasons.append("active_oco_state.json unreadable")
            hard_fail = True

    if current.git_dirty and current.startup_mode == "resume":
        reasons.append("git_dirty workspace")
        hard_fail = True

    if persisted.git_commit != current.git_commit:
        reasons.append("git_commit changed")
        hard_fail = True
    if persisted.git_branch != current.git_branch:
        reasons.append("git_branch changed")
        hard_fail = True

    if broker_snapshot is not None and local_runtime is not None:
        if broker_snapshot.has_active_orders() and not local_runtime.has_active_state():
            reasons.append("broker snapshot has open orders but local runtime has no active state")
            hard_fail = True
        if local_runtime.has_active_state() and not broker_snapshot.has_active_orders():
            reasons.append("local runtime has active state but broker snapshot is empty")
            hard_fail = True
        if broker_snapshot.has_active_orders() and local_runtime.has_broker_linked_state():
            if broker_snapshot.active_symbols() != local_runtime.broker_link_symbols:
                reasons.append("broker-linked symbols do not match broker snapshot symbols")
                hard_fail = True
            if broker_snapshot.active_order_ids() != local_runtime.linked_broker_position_ids:
                reasons.append("broker-linked position ids do not match broker snapshot order ids")
                hard_fail = True

    if hard_fail:
        verdict = RestartEligibility.RESTART_BLOCKED
    elif reasons:
        verdict = RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY
    else:
        verdict = RestartEligibility.RESTART_ELIGIBLE
    return RuntimeContextComparison(verdict=verdict, reasons=reasons)


def derive_restart_eligibility(
    comparison: RuntimeContextComparison,
) -> RestartEligibilityResult:
    return RestartEligibilityResult(
        eligibility=comparison.verdict,
        allow_new_entries=comparison.verdict is RestartEligibility.RESTART_ELIGIBLE,
        reasons=list(comparison.reasons),
    )


def write_reconciliation_report(path: Path, report: ReconciliationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# ReconciliationCycle: snapshot → optional mutation → finalize
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconciliationSnapshot:
    """Frozen view of the state used to compute a single reconciliation verdict."""

    current_metadata: RuntimeSessionMetadata
    persisted_metadata: RuntimeSessionMetadata | None
    local_state: RuntimeFileSnapshot
    broker_snapshot: "BrokerSnapshot | None"
    local_runtime: "LocalRuntimeStateSummary | None"
    comparison: RuntimeContextComparison
    restart_eligibility: RestartEligibilityResult


class ReconciliationCycle:
    """Manage startup reconciliation as snapshot → optional mutation → finalize.

    Solves the compare-then-mutate footgun: previously, ``_reconcile_startup``
    wrote a report based on a snapshot, the caller mutated state (e.g. reset
    cleanup), but the report on disk never updated. Consumers (readiness JSON,
    Grafana, operators) saw the stale verdict.

    Usage::

        cycle = ReconciliationCycle(paths=..., build_current=..., ...)
        cycle.snapshot()
        if cycle.current.restart_eligibility.eligibility == RESTART_BLOCKED and resume:
            ... fail ...
        if startup_mode == "reset":
            do_cleanup()
            cycle.invalidate_after_mutation()  # re-snapshots, must call before finalize
        cycle.finalize()  # writes report + persisted session metadata

    A finalized cycle cannot be mutated again. ``invalidate_after_mutation``
    after ``finalize`` raises ``RuntimeError``.
    """

    def __init__(
        self,
        *,
        runtime_dir: Path,
        state_db_path: Path,
        active_state_path: Path,
        session_metadata_path: Path,
        reconciliation_report_path: Path,
        broker_snapshot_path: Path,
        startup_mode: str,
        build_current_metadata: "Callable[[], RuntimeSessionMetadata]",
        load_promoted_symbols: "Callable[[], list[str]]",
        capture_broker_snapshot: "Callable[[], None] | None" = None,
    ) -> None:
        self._runtime_dir = runtime_dir
        self._state_db_path = state_db_path
        self._active_state_path = active_state_path
        self._session_metadata_path = session_metadata_path
        self._reconciliation_report_path = reconciliation_report_path
        self._broker_snapshot_path = broker_snapshot_path
        self._startup_mode = startup_mode
        self._build_current_metadata = build_current_metadata
        self._load_promoted_symbols = load_promoted_symbols
        self._capture_broker_snapshot = capture_broker_snapshot
        self._snapshot: ReconciliationSnapshot | None = None
        self._finalized = False

    @property
    def current(self) -> ReconciliationSnapshot:
        if self._snapshot is None:
            raise RuntimeError(
                "ReconciliationCycle.current accessed before snapshot() — call cycle.snapshot() first."
            )
        return self._snapshot

    def snapshot(self) -> ReconciliationSnapshot:
        """Capture current state. Idempotent — overwrites prior snapshot.

        On resume mode, also captures the broker snapshot (which represents an
        external observation, not a mutation of local state).
        """
        if self._finalized:
            raise RuntimeError("cannot snapshot a finalized ReconciliationCycle")
        current_metadata = self._build_current_metadata()
        persisted = (
            load_runtime_session_metadata(self._session_metadata_path)
            if self._session_metadata_path.exists()
            else None
        )
        local_state = inspect_runtime_files(
            self._runtime_dir,
            self._state_db_path,
            self._active_state_path,
            self._session_metadata_path,
        )
        broker_snapshot: BrokerSnapshot | None = None
        local_runtime: LocalRuntimeStateSummary | None = None
        if self._startup_mode == "resume":
            if self._capture_broker_snapshot is not None:
                self._capture_broker_snapshot()
            broker_snapshot = load_broker_snapshot(self._broker_snapshot_path)
            local_runtime = inspect_local_runtime_state(self._state_db_path)
        comparison = compare_runtime_context(
            persisted,
            current_metadata,
            local_state=local_state,
            broker_snapshot=broker_snapshot,
            local_runtime=local_runtime,
        )
        restart_eligibility = derive_restart_eligibility(comparison)
        self._snapshot = ReconciliationSnapshot(
            current_metadata=current_metadata,
            persisted_metadata=persisted,
            local_state=local_state,
            broker_snapshot=broker_snapshot,
            local_runtime=local_runtime,
            comparison=comparison,
            restart_eligibility=restart_eligibility,
        )
        return self._snapshot

    def invalidate_after_mutation(self) -> ReconciliationSnapshot:
        """Signal that local state has changed since the last snapshot.

        Wipes the prior session metadata and the on-disk reconciliation report
        (so a re-snapshot sees genuinely-fresh state — without this, a stale
        ``persisted`` would force the comparison through the persisted-match
        path even though the caller just wiped local files), then re-snapshots.
        Must be called whenever a script step mutates anything inspected by the
        reconciliation: ``state_db_path``, ``active_state_path``, or
        ``session_metadata_path``.
        """
        if self._finalized:
            raise RuntimeError(
                "cannot invalidate a finalized ReconciliationCycle — finalize is terminal"
            )
        self._session_metadata_path.unlink(missing_ok=True)
        self._reconciliation_report_path.unlink(missing_ok=True)
        return self.snapshot()

    def finalize(self) -> ReconciliationSnapshot:
        """Write reconciliation report + new persisted session metadata.

        Always uses the most recent snapshot — so if the caller called
        ``invalidate_after_mutation`` after a reset cleanup, the report
        reflects post-cleanup state, not pre-cleanup state.
        """
        if self._finalized:
            raise RuntimeError("ReconciliationCycle.finalize called twice")
        if self._snapshot is None:
            self.snapshot()
        snap = self._snapshot
        assert snap is not None
        report = ReconciliationReport(
            startup_mode=self._startup_mode,
            verdict=snap.comparison.verdict,
            reasons=list(snap.comparison.reasons),
            repaired_items=[],
            current=snap.current_metadata,
            persisted=snap.persisted_metadata,
            local_state=snap.local_state,
            local_runtime=snap.local_runtime,
            broker_snapshot=snap.broker_snapshot,
            promoted_symbols=self._load_promoted_symbols(),
            restart_eligibility=snap.restart_eligibility,
        )
        write_reconciliation_report(self._reconciliation_report_path, report)
        write_runtime_session_metadata(self._session_metadata_path, snap.current_metadata)
        self._finalized = True
        return snap

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

import duckdb


class RestartVerdict(str, Enum):
    CLEAN_RESUMABLE = "clean_resumable"
    RECONCILABLE = "reconcilable"
    INCOMPATIBLE = "incompatible"


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
class RuntimeContextComparison:
    verdict: RestartVerdict
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReconciliationReport:
    startup_mode: str
    verdict: RestartVerdict
    reasons: list[str]
    repaired_items: list[str]
    current: RuntimeSessionMetadata | None = None
    persisted: RuntimeSessionMetadata | None = None
    local_state: RuntimeFileSnapshot | None = None
    promoted_symbols: list[str] = field(default_factory=list)


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


def compare_runtime_context(
    persisted: RuntimeSessionMetadata | None,
    current: RuntimeSessionMetadata,
    local_state: RuntimeFileSnapshot | None = None,
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
            verdict=RestartVerdict.INCOMPATIBLE if hard_fail else RestartVerdict.CLEAN_RESUMABLE,
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

    if hard_fail:
        verdict = RestartVerdict.INCOMPATIBLE
    elif reasons:
        verdict = RestartVerdict.RECONCILABLE
    else:
        verdict = RestartVerdict.CLEAN_RESUMABLE
    return RuntimeContextComparison(verdict=verdict, reasons=reasons)


def write_reconciliation_report(path: Path, report: ReconciliationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")

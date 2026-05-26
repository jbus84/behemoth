"""Unified governance lock loader with LockSource protocol."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.behemoth.core.bundle_paths import BundlePaths
from src.behemoth.core.registry import CandidateSpec


class LockSource(Protocol):
    def find_lock(self, symbol: str, month: str | None = None) -> Path | None:
        ...


@dataclass(frozen=True)
class CandidateContract:
    symbol: str
    model_month: str
    cache_key: str
    candidates: list[CandidateSpec]
    bundle_paths: BundlePaths
    locked_runtime: dict[str, Any]
    cap_pips: float
    source: str
    lock_path: str | None = None


class GovernanceLockLoader:
    def __init__(self, source: LockSource) -> None:
        self._source = source

    def load_contract(self, symbol: str, month: str | None = None) -> CandidateContract:
        lock_path = self._source.find_lock(symbol, month)
        if lock_path is None:
            raise KeyError(f"No lock found for {symbol} month={month}")
        return self._parse_lock(lock_path, symbol, month)

    def _parse_lock(self, path: Path, symbol: str, month: str | None) -> CandidateContract:
        data = json.loads(path.read_text())
        sym = str(data.get("symbol", "")).upper().strip()
        bp = BundlePaths.from_lock(path)  # raises BundleIntegrityError on v1 — intentional, no fallback
        locked = data.get("locked_runtime", {}) or {}
        rows = data.get("state_universe", {}).get("rows", [])
        candidates = [CandidateSpec.from_row(r) for r in rows]

        return CandidateContract(
            symbol=sym,
            model_month=bp.model_month or (month or "unknown"),
            cache_key=f"{sym}|{month}" if month else sym,
            candidates=candidates,
            bundle_paths=bp,
            locked_runtime=dict(locked),
            cap_pips=float(locked.get("production_cap_pips", 1.2)),
            source="live" if month is None else "historical",
            lock_path=str(path),
        )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

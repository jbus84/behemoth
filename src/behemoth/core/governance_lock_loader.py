"""Unified governance lock loader with LockSource protocol."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

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
    model_binding: dict[str, Any]
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
        artifacts = data.get("artifacts", {})
        locked = data.get("locked_runtime", {})
        rows = data.get("state_universe", {}).get("rows", [])
        candidates = [CandidateSpec.from_row(r) for r in rows]
        model_binding = {
            "model_cbm_path": str(artifacts.get("model_cbm_path", "")).strip(),
            "model_cbm_sha256": str(artifacts.get("model_cbm_sha256", "")).strip(),
            "model_threshold_json_path": str(artifacts.get("model_threshold_json_path", "")).strip(),
            "model_threshold_json_sha256": str(artifacts.get("model_threshold_json_sha256", "")).strip(),
            "model_month": str(artifacts.get("model_month", "")).strip(),
        }
        return CandidateContract(
            symbol=sym,
            model_month=str(artifacts.get("model_month", month or "unknown")).strip(),
            cache_key=f"{sym}|{month}" if month else sym,
            candidates=candidates,
            model_binding=model_binding,
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

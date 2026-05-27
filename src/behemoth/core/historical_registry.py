"""Historical governance lock registry for month-aligned backtest inference.

Loads month-scoped lock manifests from:
    <history_dir>/<YYYY-MM>/<symbol>_live_lock.json

and exposes candidate/model/cap bindings by (symbol, month).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.behemoth.core.bundle_paths import BundlePaths, iter_locks
from src.behemoth.core.registry import CandidateSpec

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class HistoricalLockEntry:
    symbol: str
    month: str
    family: str
    lock_path: str
    candidates: list[CandidateSpec]
    cap_pips: float
    bundle_paths: BundlePaths


@dataclass
class HistoricalCandidateRegistry:
    """Month-aware candidate/model registry for historical replay."""

    _entries: dict[tuple[str, str, str], HistoricalLockEntry] = field(default_factory=dict)

    @classmethod
    def load(cls, history_dir: Path | str) -> HistoricalCandidateRegistry:
        p_dir = Path(history_dir)
        if not p_dir.exists() or not p_dir.is_dir():
            raise FileNotFoundError(f"Historical governance directory not found: {p_dir}")

        reg = cls()
        for month_dir in sorted(path for path in p_dir.iterdir() if path.is_dir()):
            for p in iter_locks(month_dir, family=None):
                entry = cls._load_one(p)
                if entry is not None:
                    reg._entries[(entry.symbol, entry.month, entry.family)] = entry
        return reg

    @classmethod
    def _load_one(cls, p: Path) -> HistoricalLockEntry | None:
        try:
                parent_month = p.parent.name.strip()
                if not _MONTH_RE.match(parent_month):
                    return None
                data = json.loads(p.read_text(encoding="utf-8"))
                symbol = str(data.get("symbol", "")).upper().strip()
                if not symbol:
                    return None

                # Load and validate bundle (raises BundleIntegrityError on v1 — intentional)
                bp = BundlePaths.from_lock(p)

                deploy = data.get("deployability", {}) or {}
                model_month = str(deploy.get("model_month", "")).strip() or parent_month
                if not _MONTH_RE.match(model_month):
                    return None
                if model_month != parent_month:
                    # Folder and manifest month must agree in historical mode.
                    return None

                rows = data.get("state_universe", {}).get("rows", [])
                candidates: list[CandidateSpec] = []
                if isinstance(rows, list):
                    for row in rows:
                        if isinstance(row, dict):
                            candidates.append(CandidateSpec.from_row(row, family=bp.family))
                if not candidates:
                    return None

                locked = data.get("locked_runtime", {}) if isinstance(data, dict) else {}
                cap_pips = float(locked.get("production_cap_pips", 1.2))

                return HistoricalLockEntry(
                    symbol=symbol,
                    month=model_month,
                    family=bp.family,
                    lock_path=str(p),
                    candidates=candidates,
                    cap_pips=cap_pips,
                    bundle_paths=bp,
                )
        except Exception:
            return None

    @property
    def symbols(self) -> list[str]:
        return sorted(list({k[0] for k in self._entries}))

    def months_for_symbol(self, symbol: str) -> list[str]:
        s = str(symbol).upper().strip()
        return sorted(list({m for (sym, m, _f) in self._entries if sym == s}))

    def families_for_symbol_month(self, symbol: str, month: str) -> list[str]:
        s = str(symbol).upper().strip()
        m = str(month).strip()
        return sorted(list({f for (sym, mo, f) in self._entries if sym == s and mo == m}))

    def get_entry(self, symbol: str, month: str, family: str | None = None) -> HistoricalLockEntry | None:
        s = str(symbol).upper().strip()
        m = str(month).strip()
        if family is not None:
            key = (s, m, str(family).strip())
            return self._entries.get(key)
        # Backward-compat: return single-family entry when only one exists
        matches = [e for (sym, mo, _f), e in self._entries.items() if sym == s and mo == m]
        if len(matches) == 1:
            return matches[0]
        return None

    def get_candidates(self, symbol: str, month: str, family: str | None = None) -> list[CandidateSpec]:
        e = self.get_entry(symbol, month, family=family)
        return e.candidates if e is not None else []

    def get_bundle_paths(self, symbol: str, month: str, family: str | None = None) -> BundlePaths | None:
        e = self.get_entry(symbol, month, family=family)
        return e.bundle_paths if e is not None else None

    def get_cap_pips(self, symbol: str, month: str, family: str | None = None) -> float:
        e = self.get_entry(symbol, month, family=family)
        return float(e.cap_pips) if e is not None else 1.2

    def get_lock_path(self, symbol: str, month: str, family: str | None = None) -> str | None:
        e = self.get_entry(symbol, month, family=family)
        return str(e.lock_path) if e is not None else None

    def all_candidates(self) -> list[CandidateSpec]:
        out: list[CandidateSpec] = []
        for e in self._entries.values():
            out.extend(e.candidates)
        return out

    def entry_count(self) -> int:
        """Return the total number of loaded historical lock entries."""
        return len(self._entries)

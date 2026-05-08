"""Historical governance lock registry for month-aligned backtest inference.

Loads month-scoped lock manifests from:
    <history_dir>/<YYYY-MM>/<symbol>_oco_live_lock.json

and exposes candidate/model/cap bindings by (symbol, month).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.behemoth.core.registry import CandidateSpec

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class HistoricalLockEntry:
    symbol: str
    month: str
    lock_path: str
    candidates: list[CandidateSpec]
    cap_pips: float
    model_binding: dict[str, Any]


@dataclass
class HistoricalCandidateRegistry:
    """Month-aware candidate/model registry for historical replay."""

    _entries: dict[tuple[str, str], HistoricalLockEntry] = field(default_factory=dict)

    @classmethod
    def load(cls, history_dir: Path | str) -> HistoricalCandidateRegistry:
        p_dir = Path(history_dir)
        if not p_dir.exists() or not p_dir.is_dir():
            raise FileNotFoundError(f"Historical governance directory not found: {p_dir}")

        reg = cls()
        for p in sorted(p_dir.glob("*/*_oco_live_lock.json")):
            try:
                parent_month = p.parent.name.strip()
                if not _MONTH_RE.match(parent_month):
                    continue
                data = json.loads(p.read_text(encoding="utf-8"))
                symbol = str(data.get("symbol", "")).upper().strip()
                if not symbol:
                    continue

                artifacts = data.get("artifacts", {}) if isinstance(data, dict) else {}
                model_month = str(artifacts.get("model_month", "")).strip() or parent_month
                if not _MONTH_RE.match(model_month):
                    continue
                if model_month != parent_month:
                    # Folder and manifest month must agree in historical mode.
                    continue

                rows = data.get("state_universe", {}).get("rows", [])
                candidates: list[CandidateSpec] = []
                if isinstance(rows, list):
                    for row in rows:
                        if isinstance(row, dict):
                            candidates.append(CandidateSpec.from_row(row))
                if not candidates:
                    continue

                locked = data.get("locked_runtime", {}) if isinstance(data, dict) else {}
                cap_pips = float(locked.get("production_cap_pips", 1.2))

                model_binding = {
                    "model_cbm_path": str(artifacts.get("model_cbm_path", "")).strip(),
                    "model_cbm_sha256": str(artifacts.get("model_cbm_sha256", "")).strip(),
                    "model_threshold_json_path": str(
                        artifacts.get("model_threshold_json_path", "")
                    ).strip(),
                    "model_threshold_json_sha256": str(
                        artifacts.get("model_threshold_json_sha256", "")
                    ).strip(),
                    "predictions_path": str(artifacts.get("predictions_path", "")).strip(),
                    "predictions_sha256": str(artifacts.get("predictions_sha256", "")).strip(),
                    "model_month": model_month,
                }
                if (
                    model_binding["model_cbm_path"] == ""
                    or model_binding["model_threshold_json_path"] == ""
                    or model_binding["model_cbm_sha256"] == ""
                    or model_binding["model_threshold_json_sha256"] == ""
                ):
                    continue

                key = (symbol, model_month)
                reg._entries[key] = HistoricalLockEntry(
                    symbol=symbol,
                    month=model_month,
                    lock_path=str(p),
                    candidates=candidates,
                    cap_pips=cap_pips,
                    model_binding=model_binding,
                )
            except Exception:
                continue
        return reg

    @property
    def symbols(self) -> list[str]:
        return sorted(list({k[0] for k in self._entries}))

    def months_for_symbol(self, symbol: str) -> list[str]:
        s = str(symbol).upper().strip()
        return sorted(list({m for (sym, m) in self._entries if sym == s}))

    def get_entry(self, symbol: str, month: str) -> HistoricalLockEntry | None:
        key = (str(symbol).upper().strip(), str(month).strip())
        return self._entries.get(key)

    def get_candidates(self, symbol: str, month: str) -> list[CandidateSpec]:
        e = self.get_entry(symbol, month)
        return e.candidates if e is not None else []

    def get_model_binding(self, symbol: str, month: str) -> dict[str, Any] | None:
        e = self.get_entry(symbol, month)
        return dict(e.model_binding) if e is not None else None

    def get_cap_pips(self, symbol: str, month: str) -> float:
        e = self.get_entry(symbol, month)
        return float(e.cap_pips) if e is not None else 1.2

    def get_lock_path(self, symbol: str, month: str) -> str | None:
        e = self.get_entry(symbol, month)
        return str(e.lock_path) if e is not None else None

    def all_candidates(self) -> list[CandidateSpec]:
        out: list[CandidateSpec] = []
        for e in self._entries.values():
            out.extend(e.candidates)
        return out

    def entry_count(self) -> int:
        """Return the total number of loaded historical lock entries."""
        return len(self._entries)

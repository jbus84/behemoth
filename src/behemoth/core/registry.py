"""Candidate registry loader for the OCO strategy.

Loads ``oco_rule_universe_registry.yaml`` and exposes the active
candidate specifications per symbol. Each candidate combines a symbol
with a specific horizon and barrier from the governance-locked
allowed sets.

The candidate UID format matches the WFO output:
    ``library|symbol|bar_ticks|hN|bN_hold_mode``
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_REGISTRY = Path(os.getenv("BEHEMOTH_REGISTRY_PATH", "configs/research/governance/oco_rule_universe_registry.yaml"))


@dataclass(frozen=True)
class CandidateSpec:
    """A single prediction candidate to evaluate."""

    symbol: str
    bar_ticks: int
    horizon: int
    barrier_pips: float
    candidate_uid: str
    regime_desc: str = ""

    @staticmethod
    def from_row(row: dict) -> CandidateSpec:
        """Build from a state_universe row in the live lock JSON."""
        return CandidateSpec(
            symbol=row["symbol"],
            bar_ticks=row["bar_ticks"],
            horizon=row["horizon"],
            barrier_pips=float(row["barrier_pips"]),
            candidate_uid=row["state_id"],
            regime_desc=row.get("regime_desc", ""),
        )


@dataclass
class CandidateRegistry:
    """Registry of valid candidate specifications loaded from live lock JSONs."""

    _candidates_by_symbol: dict[str, list[CandidateSpec]] = field(default_factory=dict)
    _frozen_timestamps: dict[str, str] = field(default_factory=dict)
    _caps_by_symbol: dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls, lock_dir: Path | str | None = None) -> CandidateRegistry:
        """Load exactly from per-symbol *_oco_live_lock.json files."""
        if lock_dir is None:
            lock_dir = Path(os.getenv("BEHEMOTH_GOVERNANCE_DIR", "configs/research/governance/oco"))

        import json
        p_dir = Path(lock_dir)
        if not p_dir.exists() or not p_dir.is_dir():
            raise FileNotFoundError(f"Governance live lock directory not found: {p_dir}")

        reg = cls()
        for p in p_dir.glob("*_oco_live_lock.json"):
            try:
                data = json.loads(p.read_text())
                sym = data.get("symbol", "").upper()
                if not sym:
                    continue

                rows = data.get("state_universe", {}).get("rows", [])
                candidates = [CandidateSpec.from_row(r) for r in rows]
                reg._candidates_by_symbol[sym] = candidates
                reg._frozen_timestamps[sym] = data.get("frozen_at_utc", "")

                # Extract execution cap from locked_runtime
                locked = data.get("locked_runtime", {})
                reg._caps_by_symbol[sym] = float(locked.get("production_cap_pips", 1.2))
            except Exception as e:
                import logging
                logging.getLogger("behemoth.api").error("Failed to parse %s: %s", p.name, e)

        return reg

    @property
    def symbols(self) -> list[str]:
        """Symbols that have at least one registered candidate."""
        return sorted([sym for sym, cands in self._candidates_by_symbol.items() if cands])

    def get_candidates(self, symbol: str) -> list[CandidateSpec]:
        """Return all valid candidate specs for a symbol."""
        return self._candidates_by_symbol.get(symbol.upper(), [])

    def get_cap_pips(self, symbol: str) -> float:
        """Return the locked production cap for a symbol."""
        return self._caps_by_symbol.get(symbol.upper(), 1.2)

    def all_candidates(self) -> list[CandidateSpec]:
        """Return all candidates across all symbols."""
        out: list[CandidateSpec] = []
        for cands in self._candidates_by_symbol.values():
            out.extend(cands)
        return out


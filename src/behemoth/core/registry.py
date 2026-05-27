"""Candidate registry loader for the OCO strategy.

Loads ``oco_rule_universe_registry.yaml`` and exposes the active
candidate specifications per symbol. Each candidate combines a symbol
with a specific horizon and barrier from the governance-locked
allowed sets.

The candidate UID format matches the WFO output:
    ``library|symbol|bar_ticks|hN|bN_hold_mode``
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.behemoth.core.bundle_paths import BundlePaths

_DEFAULT_REGISTRY = Path(os.getenv("BEHEMOTH_REGISTRY_PATH", "configs/research/governance/oco_rule_universe_registry.yaml"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class CandidateSpec:
    """A single prediction candidate to evaluate."""

    symbol: str
    bar_ticks: int
    horizon: int
    barrier_pips: float
    candidate_uid: str
    family: str
    regime_desc: str = ""

    @staticmethod
    def from_row(row: dict, family: str) -> CandidateSpec:
        """Build from a state_universe row in the live lock JSON.

        Rejects first_touch_clean candidates: that family's win rate was
        conditioned on ~both (look-ahead) and is not live-achievable. See
        docs/superpowers/specs/2026-05-15-oco-lookahead-bias-removal-design.md.
        """
        state_id = str(row["state_id"])
        if "first_touch_clean" in state_id:
            raise ValueError(
                f"refusing look-ahead-biased candidate '{state_id}': the "
                "first_touch_clean family conditions its win rate on ~both "
                "(future information) and must not be deployed. Re-mine and "
                "re-freeze governance on the first_touch family."
            )
        return CandidateSpec(
            symbol=row["symbol"],
            bar_ticks=row["bar_ticks"],
            horizon=row["horizon"],
            barrier_pips=float(row["barrier_pips"]),
            candidate_uid=state_id,
            regime_desc=row.get("regime_desc", ""),
            family=family,
        )


@dataclass
class CandidateRegistry:
    """Registry of valid candidate specifications loaded from live lock JSONs."""

    _candidates_by_symbol: dict[str, list[CandidateSpec]] = field(default_factory=dict)
    _frozen_timestamps: dict[str, str] = field(default_factory=dict)
    _caps_by_symbol_family: dict[tuple[str, str], float] = field(default_factory=dict)
    _bundle_paths_by_symbol_family: dict[tuple[str, str], BundlePaths] = field(default_factory=dict)  # type: ignore

    @classmethod
    def load(
        cls,
        lock_dir: Path | str | None = None,
        models_dir: Path | str | None = None,
    ) -> CandidateRegistry:
        """Load exactly from per-symbol Governance Locks."""
        if lock_dir is None:
            lock_dir = Path(os.getenv("BEHEMOTH_GOVERNANCE_DIR", "configs/research/governance/oco"))

        import json  # noqa: E402

        from src.behemoth.core.bundle_paths import BundlePaths, iter_locks  # noqa: E402

        p_dir = Path(lock_dir)
        _ = Path(models_dir) if models_dir is not None else None
        if not p_dir.exists() or not p_dir.is_dir():
            raise FileNotFoundError(f"Governance live lock directory not found: {p_dir}")

        reg = cls()
        for p in iter_locks(p_dir, family=None):
            try:
                data = json.loads(p.read_text())
                sym = data.get("symbol", "").upper()
                if not sym:
                    continue

                # Load and validate bundle (raises BundleIntegrityError on v1 — intentional)
                from src.behemoth.core.bundle_paths import BundlePaths  # noqa: E402
                bp = BundlePaths.from_lock(p)
                family = bp.family

                # Quarantine Policy: Skip if marked as not deployable
                if not bp.live_deployable:
                    import logging
                    logging.getLogger("behemoth.api").warning("Quarantining %s: live_deployable=False in governance lock.", sym)
                    continue

                rows = data.get("state_universe", {}).get("rows", [])
                candidates = [CandidateSpec.from_row(r, family=family) for r in rows]
                existing = reg._candidates_by_symbol.get(sym, [])
                reg._candidates_by_symbol[sym] = existing + candidates
                reg._frozen_timestamps[sym] = data.get("frozen_at_utc", "")

                # Extract execution cap from locked_runtime
                locked = data.get("locked_runtime", {})
                reg._caps_by_symbol_family[(sym, family)] = float(locked.get("production_cap_pips", 1.2))
                # Store BundlePaths directly, keyed by (symbol, family)
                reg._bundle_paths_by_symbol_family[(sym, family)] = bp
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

    def get_cap_pips(self, symbol: str, family: str) -> float:
        """Return the locked production cap for a symbol/family pair."""
        sym = symbol.upper()
        return self._caps_by_symbol_family.get((sym, family), 1.2)

    def get_bundle_paths(self, symbol: str, family: str) -> BundlePaths | None:  # type: ignore
        """Return frozen bundle paths for a symbol/family pair."""
        sym = symbol.upper()
        return self._bundle_paths_by_symbol_family.get((sym, family))

    def all_candidates(self) -> list[CandidateSpec]:
        """Return all candidates across all symbols."""
        out: list[CandidateSpec] = []
        for cands in self._candidates_by_symbol.values():
            out.extend(cands)
        return out

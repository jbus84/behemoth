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
from typing import Any

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
    regime_desc: str = ""

    @staticmethod
    def from_row(row: dict) -> CandidateSpec:
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
        )


@dataclass
class CandidateRegistry:
    """Registry of valid candidate specifications loaded from live lock JSONs."""

    _candidates_by_symbol: dict[str, list[CandidateSpec]] = field(default_factory=dict)
    _frozen_timestamps: dict[str, str] = field(default_factory=dict)
    _caps_by_symbol: dict[str, float] = field(default_factory=dict)
    _model_bindings_by_symbol: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        lock_dir: Path | str | None = None,
        models_dir: Path | str | None = None,
    ) -> CandidateRegistry:
        """Load exactly from per-symbol *_oco_live_lock.json files."""
        if lock_dir is None:
            lock_dir = Path(os.getenv("BEHEMOTH_GOVERNANCE_DIR", "configs/research/governance/oco"))

        import json  # noqa: E402

        from src.behemoth.core.bundle_paths import BundlePaths  # noqa: E402

        p_dir = Path(lock_dir)
        resolved_models_dir = Path(models_dir) if models_dir is not None else None
        if not p_dir.exists() or not p_dir.is_dir():
            raise FileNotFoundError(f"Governance live lock directory not found: {p_dir}")

        reg = cls()
        for p in p_dir.glob("*_oco_live_lock.json"):
            try:
                data = json.loads(p.read_text())
                sym = data.get("symbol", "").upper()
                if not sym:
                    continue

                artifacts = data.get("artifacts", {})
                BundlePaths.from_lock(p)  # raises BundleIntegrityError on v1 — intentional
                # Quarantine Policy: Skip if marked as not deployable
                deploy = data.get("deployability", {}) or {}
                deployable = bool(deploy.get("live_deployable", False))
                model_month = str(deploy.get("model_month", "")).strip()
                cbm_entry = artifacts.get("model_cbm", {}) or {}
                thr_entry = artifacts.get("model_threshold_json", {}) or {}
                cbm_path_txt = str(cbm_entry.get("path", "")).strip()
                cbm_sha = str(cbm_entry.get("sha256", "")).strip()
                thr_path_txt = str(thr_entry.get("path", "")).strip()
                thr_sha = str(thr_entry.get("sha256", "")).strip()
                if not deployable:
                    import logging
                    logging.getLogger("behemoth.api").warning("Quarantining %s: live_deployable=False in governance lock.", sym)
                    continue
                if (not cbm_path_txt) or (not cbm_sha) or (not thr_path_txt) or (not thr_sha):
                    import logging
                    logging.getLogger("behemoth.api").error(
                        "Quarantining %s: missing required model artifact hash fields in governance lock.",
                        sym,
                    )
                    continue
                cbm_path = Path(cbm_path_txt)
                thr_path = Path(thr_path_txt)
                if resolved_models_dir is not None:
                    cbm_path = resolved_models_dir / cbm_path.name
                    thr_path = resolved_models_dir / thr_path.name
                else:
                    cbm_path = p.parent / cbm_path
                    thr_path = p.parent / thr_path
                if (not cbm_path.exists()) or (not thr_path.exists()):
                    import logging
                    logging.getLogger("behemoth.api").error(
                        "Quarantining %s: locked model artifacts not found (%s, %s).",
                        sym,
                        cbm_path,
                        thr_path,
                    )
                    continue
                got_cbm_sha = _sha256(cbm_path)
                got_thr_sha = _sha256(thr_path)
                if (got_cbm_sha != cbm_sha) or (got_thr_sha != thr_sha):
                    import logging
                    logging.getLogger("behemoth.api").error(
                        "Quarantining %s: model artifact hash mismatch with governance lock.",
                        sym,
                    )
                    continue

                rows = data.get("state_universe", {}).get("rows", [])
                candidates = [CandidateSpec.from_row(r) for r in rows]
                reg._candidates_by_symbol[sym] = candidates
                reg._frozen_timestamps[sym] = data.get("frozen_at_utc", "")

                # Extract execution cap from locked_runtime
                locked = data.get("locked_runtime", {})
                reg._caps_by_symbol[sym] = float(locked.get("production_cap_pips", 1.2))
                locked_runtime_overrides: dict[str, Any] = {}
                if "threshold_mode" in locked:
                    locked_runtime_overrides["threshold_source"] = str(
                        locked.get("threshold_mode", "")
                    ).strip()
                for key in (
                    "rolling_threshold_days",
                    "rolling_threshold_min_history",
                    "execution_quantile",
                    "oco_hold_mode",
                    "oco_include_no_touch",
                ):
                    if key in locked:
                        locked_runtime_overrides[key] = locked.get(key)
                reg._model_bindings_by_symbol[sym] = {
                    "model_cbm_path": str(cbm_path),
                    "model_cbm_sha256": cbm_sha,
                    "model_threshold_json_path": str(thr_path),
                    "model_threshold_json_sha256": thr_sha,
                    "model_month": model_month,
                    "locked_runtime_overrides": locked_runtime_overrides,
                }
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

    def get_model_binding(self, symbol: str) -> dict[str, Any] | None:
        """Return frozen model artifact binding for a symbol."""
        return self._model_bindings_by_symbol.get(symbol.upper())

    def all_candidates(self) -> list[CandidateSpec]:
        """Return all candidates across all symbols."""
        out: list[CandidateSpec] = []
        for cands in self._candidates_by_symbol.values():
            out.extend(cands)
        return out

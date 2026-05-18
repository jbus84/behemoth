"""Candidate-family registry for tick-opportunity mining.

Each family supplies its own entry trigger, outcome measurement, parameter
grid, and candidate metadata. The core mining loop in
run_tick_opportunity_mining.py iterates the registry rather than branching on
a hardcoded library type.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd


@runtime_checkable
class MiningFamily(Protocol):
    name: str

    def param_grid(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        """Family-specific parameter combinations to mine (e.g. barrier
        widths). Returns at least one dict; an empty dict means no extra
        axis."""
        ...

    def entry_indices(
        self, frame: pd.DataFrame, regime_mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        """Look-ahead-free integer entry bar indices for one regime mask and
        one param combo."""
        ...

    def measure_gross(
        self, frame: pd.DataFrame, entries: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        """Gross pips realised per entry. MUST accept any entry index array
        (used for both real entries and random-baseline draws)."""
        ...

    def candidate_metadata(
        self, regime_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """family / state_id / regime_desc / ml_ready_target_type for the
        candidate row."""
        ...


_LIBRARY_TYPE_ALIASES: dict[str, list[str]] = {
    "oco": ["oco_first_touch"],
    "directional": ["directional"],
    "separate": ["oco_first_touch", "directional"],
}


def resolve_families(library_type: str) -> list[str]:
    """Map a legacy library_type string to a list of family names."""
    key = str(library_type).strip().lower()
    if key not in _LIBRARY_TYPE_ALIASES:
        raise ValueError(
            f"unknown library_type {library_type!r}; "
            f"expected one of {sorted(_LIBRARY_TYPE_ALIASES)}"
        )
    return list(_LIBRARY_TYPE_ALIASES[key])


FAMILY_REGISTRY: dict[str, MiningFamily] = {}

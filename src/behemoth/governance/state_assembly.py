"""Stage G1 state assembly for family-governed Candidate States."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.behemoth.governance.errors import CandidateSchemaError
from src.behemoth.governance.families.base import BaseFamilyGovernanceHooks


def assemble_states(
    *,
    candidates: pd.DataFrame,
    adapter: BaseFamilyGovernanceHooks,
) -> pd.DataFrame:
    """Group candidate rows into adapter-defined Candidate States."""
    state_key_cols = list(adapter.config.state_key_cols)
    missing = [col for col in state_key_cols if col not in candidates.columns]
    if missing:
        raise CandidateSchemaError(family=adapter.config.name, missing_cols=missing)

    grouped = candidates.groupby(state_key_cols, sort=False, as_index=False)
    states = grouped.agg(
        candidate_count=("candidate_id", "count"),
        train_count_sum=("train_count", "sum"),
        mean_gross_pips_train_avg=(
            "mean_gross_pips_train",
            lambda series: _weighted_average(
                series, candidates.loc[series.index, "train_count"]
            ),
        ),
    )
    states["state_id"] = states.apply(adapter.derive_state_id, axis=1)
    return states


def _weighted_average(values: pd.Series, weights: pd.Series) -> float:
    valid = values.notna() & weights.notna()
    if not valid.any():
        return float("nan")
    if float(weights[valid].sum()) == 0.0:
        return float("nan")
    return float(np.average(values[valid], weights=weights[valid]))

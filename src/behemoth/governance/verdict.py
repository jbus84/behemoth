"""Stages G4 + G5 verdict computation and roll-up."""

from __future__ import annotations

import pandas as pd

GO = "GO"
NO_GO = "NO_GO"


def compute_state_verdicts(
    *,
    selection: pd.DataFrame,
    tick_exact: pd.DataFrame,
    min_realized_pips_pass: float,
) -> pd.DataFrame:
    """Emit state-level GO iff selected and tick-exact realized pips pass."""
    joined = selection.merge(tick_exact, on="state_id", how="left")
    joined["verdict"] = [
        GO
        if selected
        and pd.notna(mean_realized_pips)
        and float(mean_realized_pips) >= float(min_realized_pips_pass)
        else NO_GO
        for selected, mean_realized_pips in zip(
            joined["selected"], joined["mean_realized_pips"], strict=True
        )
    ]
    return joined[["state_id", "verdict"]]


def compute_family_verdict(*, state_verdicts: pd.DataFrame) -> str:
    """Return GO when any state verdict is GO, otherwise NO_GO."""
    if (state_verdicts["verdict"] == GO).any():
        return GO
    return NO_GO


def compute_symbol_verdict(
    *,
    family_verdicts: dict[str, str],
    required_families: tuple[str, ...],
) -> str:
    """Return GO iff every required family verdict is GO."""
    for family in required_families:
        if family_verdicts.get(family) != GO:
            return NO_GO
    return GO

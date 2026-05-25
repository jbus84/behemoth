"""OCO first-touch family adapter for the governance framework."""

from __future__ import annotations

from src.behemoth.governance.families.base import (
    BaseFamilyGovernanceHooks,
    FamilyGovernanceConfig,
)

OCO_FIRST_TOUCH_CONFIG = FamilyGovernanceConfig(
    name="oco_first_touch",
    state_key_cols=("family", "barrier_pips", "horizon", "regime"),
    wfo_target_col="y_oco_first_touch_decided",
    payoff_simulator="barrier_touch",
    selection_gate_cols=("both_window_rate", "p_up_first"),
    schema_version="oco_v4.0",
)


class OcoFirstTouchHooks(BaseFamilyGovernanceHooks):
    """OCO first-touch adapter stub."""


OCO_FIRST_TOUCH_HOOKS = OcoFirstTouchHooks(OCO_FIRST_TOUCH_CONFIG)

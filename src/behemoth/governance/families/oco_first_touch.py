"""OCO first-touch family adapter for the governance framework."""

from __future__ import annotations

from src.behemoth.governance.families.base import (
    BaseFamilyGovernanceHooks,
    FamilyGovernanceConfig,
)

OCO_FIRST_TOUCH_CONFIG = FamilyGovernanceConfig(
    name="oco_first_touch",
    state_key_cols=("family", "bar_ticks", "barrier_pips", "horizon", "regime"),
    wfo_target_col="y_oco_first_touch_decided",
    payoff_simulator="barrier_touch",
    selection_gate_cols=("both_window_rate", "p_up_first"),
    schema_version="oco_v4.0",
)


class OcoFirstTouchHooks(BaseFamilyGovernanceHooks):
    """OCO first-touch adapter."""

    def selection_gate(self, row, thresholds):
        return (
            float(row["both_window_rate"]) >= float(thresholds["min_both_window_rate"])
            and float(row["p_up_first"]) >= float(thresholds["min_p_up_first"])
        )


OCO_FIRST_TOUCH_HOOKS = OcoFirstTouchHooks(OCO_FIRST_TOUCH_CONFIG)

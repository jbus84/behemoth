import pytest

from src.behemoth.governance.families.base import (
    BaseFamilyGovernanceHooks,
    FamilyGovernanceConfig,
)


def test_family_governance_config_requires_all_fields():
    with pytest.raises(TypeError):
        FamilyGovernanceConfig(name="x")  # type: ignore[call-arg]


def test_family_governance_config_holds_values():
    cfg = FamilyGovernanceConfig(
        name="oco_first_touch",
        state_key_cols=("family", "barrier_pips", "horizon", "regime"),
        wfo_target_col="y_oco_first_touch_decided",
        payoff_simulator="barrier_touch",
        selection_gate_cols=("both_window_rate", "p_up_first"),
        schema_version="oco_v4.0",
    )
    assert cfg.name == "oco_first_touch"
    assert cfg.payoff_simulator == "barrier_touch"


def test_family_governance_config_rejects_unknown_simulator():
    with pytest.raises(ValueError, match="payoff_simulator"):
        FamilyGovernanceConfig(
            name="x",
            state_key_cols=("a",),
            wfo_target_col="t",
            payoff_simulator="not_a_simulator",  # type: ignore[arg-type]
            selection_gate_cols=(),
            schema_version="v1",
        )


def test_family_governance_config_is_frozen():
    cfg = FamilyGovernanceConfig(
        name="x",
        state_key_cols=("a",),
        wfo_target_col="t",
        payoff_simulator="forward_return",
        selection_gate_cols=(),
        schema_version="v1",
    )
    with pytest.raises(Exception):
        cfg.name = "y"  # type: ignore[misc]


def test_base_hooks_default_derive_state_id_uses_state_key_cols_in_order():
    import pandas as pd

    cfg = FamilyGovernanceConfig(
        name="oco_first_touch",
        state_key_cols=("family", "barrier_pips", "horizon", "regime"),
        wfo_target_col="t",
        payoff_simulator="barrier_touch",
        selection_gate_cols=(),
        schema_version="v1",
    )
    hooks = BaseFamilyGovernanceHooks(config=cfg)
    row = pd.Series(
        {
            "family": "oco_first_touch",
            "barrier_pips": 2.0,
            "horizon": 3,
            "regime": "london",
        }
    )
    sid = hooks.derive_state_id(row)
    assert "oco_first_touch" in sid
    assert "2" in sid and "3" in sid and "london" in sid


def test_base_hooks_default_selection_gate_returns_true():
    import pandas as pd

    cfg = FamilyGovernanceConfig(
        name="x",
        state_key_cols=("a",),
        wfo_target_col="t",
        payoff_simulator="forward_return",
        selection_gate_cols=(),
        schema_version="v1",
    )
    hooks = BaseFamilyGovernanceHooks(config=cfg)
    assert hooks.selection_gate(pd.Series({}), {}) is True

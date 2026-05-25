import textwrap
from pathlib import Path

import pytest

from src.behemoth.governance.errors import (
    InvalidModelMonthError,
    MissingGovernanceFieldError,
    RequiredFamilyMissingThresholdsError,
    UnknownFamilyError,
)
from src.behemoth.governance.symbol_config import load_symbol_governance_config


def _write_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "eurusd_governance.yaml"
    p.write_text(textwrap.dedent(body))
    return p


def test_loads_valid_yaml(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
        symbol: EURUSD
        model_month: 2026-05
        required_families:
          - oco_first_touch
        families:
          oco_first_touch:
            capacity_floor_monthly: 200
            capacity_floor_annual: 500
            max_state_churn: 0.45
            max_top_state_share: 0.35
            max_state_hhi: 0.25
            state_train_months: 2
            min_states: 1
            max_states: 12
            selection_gates:
              min_both_window_rate: 0.0
              min_p_up_first: 0.0
        """,
    )
    cfg = load_symbol_governance_config(p)
    assert cfg.symbol == "EURUSD"
    assert cfg.model_month == "2026-05"
    assert cfg.required_families == ("oco_first_touch",)
    assert cfg.families["oco_first_touch"]["capacity_floor_monthly"] == 200


def test_missing_top_level_field_raises(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
        symbol: EURUSD
        required_families: [oco_first_touch]
        families: {oco_first_touch: {}}
        """,
    )
    with pytest.raises(MissingGovernanceFieldError) as ei:
        load_symbol_governance_config(p)
    assert ei.value.field == "model_month"


def test_invalid_model_month_format_raises(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
        symbol: EURUSD
        model_month: 2026/05
        required_families: [oco_first_touch]
        families:
          oco_first_touch:
            capacity_floor_monthly: 200
            capacity_floor_annual: 500
            max_state_churn: 0.45
            max_top_state_share: 0.35
            max_state_hhi: 0.25
            state_train_months: 2
            min_states: 1
            max_states: 12
            selection_gates: {}
        """,
    )
    with pytest.raises(InvalidModelMonthError):
        load_symbol_governance_config(p)


def test_required_family_not_in_families_raises(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
        symbol: EURUSD
        model_month: 2026-05
        required_families: [directional_run]
        families:
          oco_first_touch:
            capacity_floor_monthly: 200
            capacity_floor_annual: 500
            max_state_churn: 0.45
            max_top_state_share: 0.35
            max_state_hhi: 0.25
            state_train_months: 2
            min_states: 1
            max_states: 12
            selection_gates: {}
        """,
    )
    with pytest.raises(RequiredFamilyMissingThresholdsError) as ei:
        load_symbol_governance_config(p)
    assert ei.value.family == "directional_run"


def test_required_families_must_not_be_empty(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
        symbol: EURUSD
        model_month: 2026-05
        required_families: []
        families: {}
        """,
    )
    with pytest.raises(MissingGovernanceFieldError) as ei:
        load_symbol_governance_config(p)
    assert ei.value.field == "required_families"


def test_unknown_family_name_raises(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
        symbol: EURUSD
        model_month: 2026-05
        required_families: [not_a_family]
        families:
          not_a_family:
            capacity_floor_monthly: 200
            capacity_floor_annual: 500
            max_state_churn: 0.45
            max_top_state_share: 0.35
            max_state_hhi: 0.25
            state_train_months: 2
            min_states: 1
            max_states: 12
            selection_gates: {}
        """,
    )
    with pytest.raises(UnknownFamilyError):
        load_symbol_governance_config(p)


def test_missing_per_family_field_raises(tmp_path):
    p = _write_yaml(
        tmp_path,
        """
        symbol: EURUSD
        model_month: 2026-05
        required_families: [oco_first_touch]
        families:
          oco_first_touch:
            capacity_floor_annual: 500
            max_state_churn: 0.45
            max_top_state_share: 0.35
            max_state_hhi: 0.25
            state_train_months: 2
            min_states: 1
            max_states: 12
            selection_gates: {}
        """,
    )
    with pytest.raises(MissingGovernanceFieldError) as ei:
        load_symbol_governance_config(p)
    assert ei.value.field == "capacity_floor_monthly"
    assert ei.value.family == "oco_first_touch"


def test_active_symbol_governance_configs_load():
    for symbol in ("eurusd", "gbpusd", "usdjpy", "usdchf", "audusd", "usdcad"):
        cfg = load_symbol_governance_config(
            Path(f"configs/research/experiments/{symbol}_governance.yaml")
        )
        assert cfg.symbol == symbol.upper()
        assert cfg.required_families == ("oco_first_touch",)

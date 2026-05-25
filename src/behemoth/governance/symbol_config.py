"""Symbol governance config loader with no silent defaults."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.behemoth.governance.errors import (
    InvalidModelMonthError,
    MissingGovernanceFieldError,
    RequiredFamilyMissingThresholdsError,
    UnknownFamilyError,
)

REQUIRED_PER_FAMILY_FIELDS: tuple[str, ...] = (
    "capacity_floor_monthly",
    "capacity_floor_annual",
    "max_state_churn",
    "max_top_state_share",
    "max_state_hhi",
    "state_train_months",
    "min_states",
    "max_states",
    "selection_gates",
)

_MODEL_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class SymbolGovernanceConfig:
    """Loaded view of one symbol's governance YAML."""

    symbol: str
    model_month: str
    required_families: tuple[str, ...]
    families: dict[str, dict[str, Any]]


def load_symbol_governance_config(yaml_path: Path) -> SymbolGovernanceConfig:
    """Load and validate a symbol governance YAML."""
    raw = yaml.safe_load(Path(yaml_path).read_text())
    if not isinstance(raw, dict):
        raise MissingGovernanceFieldError(symbol="?", family="?", field="(empty YAML)")

    symbol = raw.get("symbol")
    if symbol is None:
        raise MissingGovernanceFieldError(symbol="?", family="(top-level)", field="symbol")

    for top_field in ("model_month", "required_families", "families"):
        if top_field not in raw:
            raise MissingGovernanceFieldError(
                symbol=str(symbol), family="(top-level)", field=top_field
            )

    model_month = str(raw["model_month"])
    if not _MODEL_MONTH_RE.match(model_month):
        raise InvalidModelMonthError(value=model_month)

    required_families = tuple(raw["required_families"])
    if not required_families:
        raise MissingGovernanceFieldError(
            symbol=str(symbol), family="(top-level)", field="required_families"
        )

    families_block = dict(raw["families"])

    for family in required_families:
        if family not in families_block:
            raise RequiredFamilyMissingThresholdsError(
                symbol=str(symbol), family=str(family)
            )

    from src.behemoth.governance.families import FAMILY_GOVERNANCE_REGISTRY

    for family in families_block:
        if family not in FAMILY_GOVERNANCE_REGISTRY:
            raise UnknownFamilyError(family=str(family))

    for family, thresholds in families_block.items():
        if not isinstance(thresholds, dict):
            raise MissingGovernanceFieldError(
                symbol=str(symbol), family=str(family), field="(non-dict block)"
            )
        for field in REQUIRED_PER_FAMILY_FIELDS:
            if field not in thresholds:
                raise MissingGovernanceFieldError(
                    symbol=str(symbol), family=str(family), field=field
                )

    return SymbolGovernanceConfig(
        symbol=str(symbol),
        model_month=model_month,
        required_families=required_families,
        families=families_block,
    )

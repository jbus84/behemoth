"""Family adapter registry."""

from __future__ import annotations

from src.behemoth.governance.errors import UnknownFamilyError
from src.behemoth.governance.families.base import (
    BaseFamilyGovernanceHooks,
    FamilyGovernanceConfig,
)
from src.behemoth.governance.families.oco_first_touch import OCO_FIRST_TOUCH_HOOKS

FAMILY_GOVERNANCE_REGISTRY: dict[str, BaseFamilyGovernanceHooks] = {
    OCO_FIRST_TOUCH_HOOKS.config.name: OCO_FIRST_TOUCH_HOOKS,
}


def get_family_adapter(name: str) -> BaseFamilyGovernanceHooks:
    """Lookup a registered family adapter by name."""
    if name not in FAMILY_GOVERNANCE_REGISTRY:
        raise UnknownFamilyError(family=name)
    return FAMILY_GOVERNANCE_REGISTRY[name]


__all__ = [
    "BaseFamilyGovernanceHooks",
    "FAMILY_GOVERNANCE_REGISTRY",
    "FamilyGovernanceConfig",
    "get_family_adapter",
]

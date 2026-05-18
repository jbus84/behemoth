"""Contract: the OCO mining pipeline emits only look-ahead-free families.

The clean variant was removed because its universe was conditioned on
~both (both barriers touched within the horizon — future information). Any
new OCO family must be audited for look-ahead before being added to ALLOWED.
See docs/superpowers/specs/2026-05-15-oco-lookahead-bias-removal-design.md.

Since the family-framework refactor (sub-project 0) candidate families live
in `FAMILY_REGISTRY` rather than a hardcoded loop, so this contract inspects
the registry directly.
"""
from __future__ import annotations

ALLOWED_OCO_FAMILIES = {"oco_first_touch", "oco_asymmetric"}


def test_mining_family_definitions_are_allowlisted() -> None:
    from scripts.mining_family import FAMILY_REGISTRY

    oco_families = {name for name in FAMILY_REGISTRY if name.startswith("oco_")}
    assert oco_families <= ALLOWED_OCO_FAMILIES, (
        f"non-allowlisted OCO family registered: {oco_families - ALLOWED_OCO_FAMILIES}. "
        f"Audit it for look-ahead conditioning before adding to ALLOWED_OCO_FAMILIES."
    )
    assert oco_families == ALLOWED_OCO_FAMILIES, (
        f"expected exactly {ALLOWED_OCO_FAMILIES}, got {oco_families}"
    )

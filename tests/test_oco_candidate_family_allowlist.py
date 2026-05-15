"""Contract: the OCO mining pipeline emits only look-ahead-free families.

The clean variant was removed because its universe was conditioned on
~both (both barriers touched within the horizon — future information). Any
new family must be audited for look-ahead before being added to ALLOWED.
See docs/superpowers/specs/2026-05-15-oco-lookahead-bias-removal-design.md.
"""
from __future__ import annotations

import ast
from pathlib import Path

ALLOWED_OCO_FAMILIES = {"oco_first_touch"}


def test_mining_family_definitions_are_allowlisted() -> None:
    src = (
        Path(__file__).parents[1]
        / "scripts"
        / "run_tick_opportunity_mining.py"
    ).read_text(encoding="utf-8")
    parts = src.split('for fam, fam_mask in [', 1)
    if len(parts) < 2:
        raise AssertionError("Could not find family loop in mining script")
    block = parts[1].split(']:', 1)[0]
    try:
        tree = ast.parse("[" + block + "]", mode="eval")
    except SyntaxError as exc:
        raise AssertionError(f"Could not parse family loop body: {exc}") from exc
    list_node = tree.body
    if not isinstance(list_node, ast.List):
        raise AssertionError("Family loop body is not a list literal")
    names: set[str] = set()
    for elt in list_node.elts:
        if isinstance(elt, ast.Tuple) and len(elt.elts) >= 1:
            first = elt.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.add(first.value)
    families = {f"oco_{n}" for n in names}
    assert families <= ALLOWED_OCO_FAMILIES, (
        f"non-allowlisted OCO family emitted: {families - ALLOWED_OCO_FAMILIES}. "
        f"Audit it for look-ahead conditioning before adding to ALLOWED_OCO_FAMILIES."
    )
    assert families == ALLOWED_OCO_FAMILIES, (
        f"expected exactly {ALLOWED_OCO_FAMILIES}, got {families}"
    )

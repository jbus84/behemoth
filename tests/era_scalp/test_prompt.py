from __future__ import annotations


def test_scalp_rules_cover_contract_and_causality():
    from scripts.era.llm import build_prompt
    from scripts.era_scalp.prompt import FEATURE_NAMES, SCALP_RULES

    p = build_prompt("def signal(ctx):\n    return ctx.col('vel_z_h1')\n", 0.0, "", "idea",
                     rules=SCALP_RULES).lower()
    assert "signal(ctx)" in p
    assert "future" in p and ("trailing" in p or "expanding" in p)
    assert "ctx.col" in p
    assert "vel_z_h1" in p and "spread_z" in p
    assert "vel_z_h1" in FEATURE_NAMES and "y_fwd" not in " ".join(FEATURE_NAMES)

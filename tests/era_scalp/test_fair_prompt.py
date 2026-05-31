def test_fair_rules_cover_contract():
    from scripts.era.llm import build_prompt
    from scripts.era_scalp.fair_prompt import FAIR_FEATURE_NAMES, FAIR_RULES

    p = build_prompt("def fair(ctx):\n    return ctx.col('vel_pips_h1')\n", 0.0, "", "idea",
                     rules=FAIR_RULES).lower()
    assert "fair(ctx)" in p
    assert "mispricing" in p or "fair - mid" in p or "fair minus mid" in p
    assert "pip" in p
    assert "future" in p and ("trailing" in p or "expanding" in p or "ewma" in p)
    assert "vel_pips_h1" in p
    assert "y_fwd" not in " ".join(FAIR_FEATURE_NAMES)

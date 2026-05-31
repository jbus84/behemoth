def test_fade_rules_cover_contract():
    from scripts.era.llm import build_prompt
    from scripts.era_scalp.fade_prompt import FADE_FEATURE_NAMES, FADE_RULES

    p = build_prompt("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n", 0.0, "", "idea",
                     rules=FADE_RULES).lower()
    assert "signal(ctx)" in p
    assert "fade" in p and "fair" in p
    assert "nan" in p and ("gate" in p or "abstain" in p)
    assert "future" in p and ("trailing" in p or "expanding" in p or "ewma" in p)
    assert "mean-revert" in p or "variance ratio" in p
    assert "vel_pips_h1" in p
    assert "y_fwd" not in " ".join(FADE_FEATURE_NAMES)

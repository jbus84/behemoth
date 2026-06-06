def test_range_rules_cover_deploy_contract():
    from scripts.era.llm import build_prompt
    from scripts.era_scalp.range_prompt import DEPLOY_FEATURE_NAMES, RANGE_RULES

    p = build_prompt("def deploy(ctx):\n    return ctx.col('range_pips')\n", 0.0, "", "idea",
                     rules=RANGE_RULES).lower()
    assert "deploy(ctx)" in p
    assert "non-directional" in p or "not predict a direction" in p
    assert "future" in p and ("trailing" in p or "expanding" in p)
    assert "range_pips" in p
    assert "range_pips" in DEPLOY_FEATURE_NAMES and "y_fwd" not in " ".join(DEPLOY_FEATURE_NAMES)

import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fade_seeds import (
    BRANCH_TAXONOMY,
    CROSS_BRANCH_INDEX,
    FADE_SEED_PROGRAMS,
    RICH_TEMPLATES,
    SEED_BRANCH_TAGS,
)
from scripts.era_scalp.load_splits import WHITELIST
from scripts.era_scalp.sandbox import causality_probe, run_program

NEW = {"ofp_continuation": "order_flow_persistence", "amihud_liquidity_gate": "liquidity_amihud"}


def _ctx(n=800, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(WHITELIST)))
    X[:, WHITELIST.index("tick_volume")] = np.abs(X[:, WHITELIST.index("tick_volume")]) * 50 + 1
    return FeatureContext(X=X, names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def test_new_branches_registered():
    for seed, branch in NEW.items():
        assert branch in BRANCH_TAXONOMY, branch
        assert branch in RICH_TEMPLATES, branch
        assert SEED_BRANCH_TAGS[seed] == branch
        assert seed in FADE_SEED_PROGRAMS


def test_new_seeds_run_and_causal():
    ctx = _ctx()
    for seed in NEW:
        src = FADE_SEED_PROGRAMS[seed]
        sig, err, _ = run_program(src, ctx)
        assert err is None, f"{seed}: {err}"
        assert sig.shape == (ctx.n_bars,)
        assert np.isfinite(sig).sum() > 0, f"{seed}: all-nan"
        ok, reason = causality_probe(src, ctx, sig)
        assert ok, f"{seed}: {reason}"


def test_new_branches_have_cross_prompts():
    assert ("order_flow_persistence", "mean_reversion_gate") in CROSS_BRANCH_INDEX
    assert ("liquidity_amihud", "mean_reversion_gate") in CROSS_BRANCH_INDEX
    assert ("mean_reversion_gate", "liquidity_amihud") in CROSS_BRANCH_INDEX

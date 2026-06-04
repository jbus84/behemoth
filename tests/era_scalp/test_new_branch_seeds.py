import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fade_seeds import (
    BRANCH_TAXONOMY,
    CROSS_BRANCH_INDEX,
    FADE_SEED_PROGRAMS,
    RICH_TEMPLATES,
    SEED_BRANCH_TAGS,
)
from scripts.era_scalp.sandbox import causality_probe, run_program

NAMES = [
    "spread_pips", "spread_z", "tick_volume", "tick_rate_hz", "tick_rate_z",
    "tick_burst", "tick_burst_score", "high_pos_tick", "low_pos_tick",
    "hl_pos_delta_tick", "bar_return_sign", "vel_pips_h1", "vel_pips_h2",
    "vel_pips_h5", "vel_pips_h10", "vel_z_h1", "vel_z_h2", "vel_z_h5",
    "vel_z_h10", "accel_pips", "hour_utc", "bar_range_pips",
]


def _ctx(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(NAMES)))
    X[:, NAMES.index("tick_volume")] = np.abs(X[:, NAMES.index("tick_volume")]) * 50 + 1
    X[:, NAMES.index("hl_pos_delta_tick")] = np.clip(X[:, NAMES.index("hl_pos_delta_tick")], -1, 1)
    X[:, NAMES.index("bar_return_sign")] = np.sign(X[:, NAMES.index("bar_return_sign")])
    X[:, NAMES.index("bar_range_pips")] = np.abs(X[:, NAMES.index("bar_range_pips")]) + 0.5
    return FeatureContext(X=X, names=list(NAMES), hour=(np.arange(n) % 24).astype(float))


def test_microprice_branch_registered():
    assert "microprice" in BRANCH_TAXONOMY
    assert "microprice" in RICH_TEMPLATES
    assert SEED_BRANCH_TAGS["microprice_fade"] == "microprice"
    assert "microprice_fade" in FADE_SEED_PROGRAMS


def test_microprice_seed_runs_and_is_causal():
    ctx = _ctx()
    src = FADE_SEED_PROGRAMS["microprice_fade"]
    sig, err, _ = run_program(src, ctx)
    assert err is None, err
    assert sig.shape == (ctx.n_bars,)
    assert np.isfinite(sig).sum() > 0
    ok, reason = causality_probe(src, ctx, sig)
    assert ok, reason


def test_vpin_branch_registered():
    assert "flow_toxicity" in BRANCH_TAXONOMY
    assert "flow_toxicity" in RICH_TEMPLATES
    assert SEED_BRANCH_TAGS["vpin_gated_fade"] == "flow_toxicity"
    assert "vpin_gated_fade" in FADE_SEED_PROGRAMS


def test_vpin_seed_runs_and_is_causal():
    ctx = _ctx(seed=1)
    src = FADE_SEED_PROGRAMS["vpin_gated_fade"]
    sig, err, _ = run_program(src, ctx)
    assert err is None, err
    assert sig.shape == (ctx.n_bars,)
    assert np.isfinite(sig).sum() > 0
    ok, reason = causality_probe(src, ctx, sig)
    assert ok, reason


def test_new_branches_have_cross_prompts():
    assert ("microprice", "mean_reversion_gate") in CROSS_BRANCH_INDEX
    assert ("flow_toxicity", "mean_reversion_gate") in CROSS_BRANCH_INDEX
    assert ("mean_reversion_gate", "microprice") in CROSS_BRANCH_INDEX

import numpy as np

from scripts.era_scalp.atomic_concepts import (
    COMBINATION_OPERATORS,
    CONCEPT_TAXONOMY,
    SKELETONS,
    _auto_upgrade_skeleton,
    render_composition,
)
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.load_splits import WHITELIST
from scripts.era_scalp.sandbox import causality_probe, run_program

P = {"alpha": 0.05, "mult": 0.5, "lam": 0.5, "W": 50, "beta": 0.5, "k": 3.0,
     "scale": 0.5, "w_base": 1.0, "w_corr": 1.0, "w_corr2": 1.0, "w_cal": 0.0}


def _ctx(n=500, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(WHITELIST)))
    X[:, WHITELIST.index("tick_volume")] = np.abs(X[:, WHITELIST.index("tick_volume")]) * 50 + 1
    X[:, WHITELIST.index("bar_range_pips")] = np.abs(X[:, WHITELIST.index("bar_range_pips")]) + 0.5
    return FeatureContext(X=X, names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def test_registered():
    assert "base_plus_two_corrections" in SKELETONS
    assert "two_correction_additive" in COMBINATION_OPERATORS
    assert CONCEPT_TAXONOMY["two_correction_additive"][0] == "combination"


def test_auto_upgrade_routes_correction2():
    up = _auto_upgrade_skeleton("simple", {"base": "slow_ewma", "correction": "roll_bounce",
                                           "correction2": "ofi_imbalance", "combination": "two_correction_additive"})
    assert up == "base_plus_two_corrections"


def test_two_correction_renders_runs_causal():
    ctx = _ctx()
    src = render_composition("base_plus_two_corrections",
                             {"base": "slow_ewma", "correction": "roll_bounce",
                              "correction2": "bouchaud_propagator", "combination": "two_correction_additive"}, P)
    out, err, _ = run_program(src, ctx, required_fn="estimate_fair")
    assert err is None, err
    assert out.shape == (ctx.n_bars,) and np.isfinite(out).sum() > 0
    ok, reason = causality_probe(src, ctx, out, required_fn="estimate_fair")
    assert ok, reason


def test_both_corrections_contribute():
    ctx = _ctx(seed=3)
    ops = {"base": "slow_ewma", "correction": "roll_bounce",
           "correction2": "bouchaud_propagator", "combination": "two_correction_additive"}
    on, e1, _ = run_program(render_composition("base_plus_two_corrections", ops, {**P, "w_corr2": 1.0}), ctx, required_fn="estimate_fair")
    off, e2, _ = run_program(render_composition("base_plus_two_corrections", ops, {**P, "w_corr2": 0.0}), ctx, required_fn="estimate_fair")
    assert e1 is None and e2 is None
    m = np.isfinite(on) & np.isfinite(off)
    assert m.any() and not np.allclose(on[m], off[m])   # correction2 (correction_b) is wired & contributes


def test_single_correction_regression():
    ctx = _ctx(seed=4)
    out, err, _ = run_program(render_composition("base_plus_correction",
                              {"base": "slow_ewma", "correction": "roll_bounce", "combination": "additive_blend"}, P),
                              ctx, required_fn="estimate_fair")
    assert err is None and np.isfinite(out).sum() > 0

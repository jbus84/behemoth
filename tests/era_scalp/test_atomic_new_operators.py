import numpy as np

from scripts.era_scalp.atomic_concepts import (
    CONCEPT_TAXONOMY,
    MICROSTRUCTURE_CORRECTIONS,
    VOLATILITY_ADAPTATIONS,
    render_composition,
)
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.load_splits import WHITELIST
from scripts.era_scalp.sandbox import causality_probe, run_program

NEW_MICRO = ["amihud_illiquidity", "bouchaud_propagator", "kyle_lambda_regression", "bns_bipower_jump"]
NEW_VOL = ["acd_intensity"]


def _ctx(n=600, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(WHITELIST)))
    X[:, WHITELIST.index("tick_volume")] = np.abs(X[:, WHITELIST.index("tick_volume")]) * 50 + 1
    X[:, WHITELIST.index("range_pips")] = np.abs(X[:, WHITELIST.index("range_pips")]) + 0.5
    return FeatureContext(X=X, names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def test_new_operators_registered():
    for k in NEW_MICRO:
        assert k in MICROSTRUCTURE_CORRECTIONS, k
        assert k in CONCEPT_TAXONOMY, k
    for k in NEW_VOL:
        assert k in VOLATILITY_ADAPTATIONS, k
        assert k in CONCEPT_TAXONOMY, k


def test_new_micro_operators_render_run_causal():
    ctx = _ctx()
    params = {"alpha": 0.05, "lam": 0.5, "W": 50, "beta": 0.5, "k": 3.0, "scale": 0.5,
              "w_base": 1.0, "w_corr": 1.0, "w_cal": 0.0}
    for op in NEW_MICRO:
        src = render_composition("base_plus_correction",
                                 {"base": "slow_ewma", "correction": op, "combination": "additive_blend"},
                                 params)
        out, err, _ = run_program(src, ctx, required_fn="estimate_fair")
        assert err is None, f"{op}: {err}"
        assert out.shape == (ctx.n_bars,), f"{op}: shape"
        assert np.isfinite(out).sum() > 0, f"{op}: all-nan"
        ok, reason = causality_probe(src, ctx, out, required_fn="estimate_fair")
        assert ok, f"{op}: {reason}"


def test_acd_intensity_vol_adaptive_causal():
    ctx = _ctx(seed=2)
    src = render_composition("vol_adaptive",
                             {"vol_adaptation": "acd_intensity", "base": "adaptive_ewma",
                              "correction": "roll_bounce", "combination": "additive_blend"},
                             {"alpha_min": 0.02, "alpha_max": 0.10, "W": 20, "mult": 0.5,
                              "w_base": 1.0, "w_corr": -1.0, "w_cal": 0.0})
    out, err, _ = run_program(src, ctx, required_fn="estimate_fair")
    assert err is None, err
    ok, reason = causality_probe(src, ctx, out, required_fn="estimate_fair")
    assert ok, reason

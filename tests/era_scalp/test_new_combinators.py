import numpy as np

from scripts.era_scalp.atomic_concepts import (
    COMBINATION_OPERATORS,
    CONCEPT_TAXONOMY,
    render_composition,
)
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.load_splits import WHITELIST
from scripts.era_scalp.sandbox import causality_probe, run_program

NEW = ["clipped_blend", "zscore_blend", "soft_gate"]
PARAMS = {"alpha": 0.05, "mult": 0.5, "k": 3.0, "gamma": 1.0, "threshold": 0.5,
          "w_base": 1.0, "w_corr": 1.0, "w_cal": 0.0}


def _ctx(n=500, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(WHITELIST)))
    X[:, WHITELIST.index("range_pips")] = np.abs(X[:, WHITELIST.index("range_pips")]) + 0.5
    return FeatureContext(X=X, names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def test_new_combinators_registered():
    for c in NEW:
        assert c in COMBINATION_OPERATORS, c
        assert c in CONCEPT_TAXONOMY and CONCEPT_TAXONOMY[c][0] == "combination", c


def test_combinators_render_run_causal_in_base_plus_correction():
    ctx = _ctx()
    for comb in NEW:
        src = render_composition("base_plus_correction",
                                 {"base": "slow_ewma", "correction": "roll_bounce", "combination": comb},
                                 PARAMS)
        out, err, _ = run_program(src, ctx, required_fn="estimate_fair")
        assert err is None, f"{comb}: {err}"
        assert out.shape == (ctx.n_bars,) and np.isfinite(out).sum() > 0, f"{comb}: bad output"
        ok, reason = causality_probe(src, ctx, out, required_fn="estimate_fair")
        assert ok, f"{comb}: {reason}"


def test_soft_gate_uses_vol_adapted_when_present():
    ctx = _ctx(seed=2)
    src = render_composition("vol_adaptive",
                             {"vol_adaptation": "realized_vol_gate", "base": "slow_ewma",
                              "correction": "roll_bounce", "combination": "soft_gate"},
                             {**PARAMS, "W": 20})
    out, err, _ = run_program(src, ctx, required_fn="estimate_fair")
    assert err is None, err
    ok, reason = causality_probe(src, ctx, out, required_fn="estimate_fair")
    assert ok, reason

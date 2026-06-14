import numpy as np

from scripts.era_scalp.atomic_concepts import render_composition
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.load_splits import WHITELIST
from scripts.era_scalp.sandbox import run_program


def _ctx(n=300, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(WHITELIST)))
    X[:, WHITELIST.index("range_pips")] = np.abs(X[:, WHITELIST.index("range_pips")]) + 0.5
    return FeatureContext(X=X, names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def test_render_handles_list_operator_value():
    # malformed LLM composition: a slot maps to a LIST of op-names instead of a string
    src = render_composition(
        "base_plus_correction",
        {"base": "slow_ewma", "correction": ["roll_bounce", "ofi_imbalance"], "combination": "additive_blend"},
        {"alpha": 0.05, "w_base": 1.0, "w_corr": 1.0, "w_cal": 0.0},
    )
    assert "def estimate_fair(ctx)" in src          # must not raise
    out, err, _ = run_program(src, _ctx(), required_fn="estimate_fair")
    assert err is None and out.shape == (300,)       # degenerate but valid & runnable


def test_render_handles_non_string_in_any_slot():
    src = render_composition(
        "base_plus_two_corrections",
        {"base": ["x"], "correction": "roll_bounce", "correction2": 123,
         "combination": "two_correction_additive"},
        {"mult": 0.5, "w_base": 1.0, "w_corr": 1.0, "w_corr2": 1.0},
    )
    assert "def estimate_fair(ctx)" in src
    out, err, _ = run_program(src, _ctx(seed=2), required_fn="estimate_fair")
    assert err is None


def test_render_handles_non_dict_params():
    src = render_composition(
        "base_plus_correction",
        {"base": "slow_ewma", "correction": "roll_bounce", "combination": "additive_blend"},
        ["not", "a", "dict"],
    )
    assert "def estimate_fair(ctx)" in src
    out, err, _ = run_program(src, _ctx(seed=3), required_fn="estimate_fair")
    assert err is None

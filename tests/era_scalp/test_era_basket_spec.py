import numpy as np

from scripts.era_scalp.basket_context import BasketSplit
from scripts.era_scalp.basket_seeds import BASKET_SEED_PROGRAMS
from scripts.era_scalp.era_basket import basket_spec
from scripts.era_scalp.era_engine import score_program


def _split(n=40, m=6, seed=2):
    rng = np.random.default_rng(seed)
    return BasketSplit(
        r=rng.standard_normal((n, m)),
        y_fwd_panel=rng.standard_normal((n, m)) * 0.5,
        cost_panel=np.full((n, m), 0.1),
        names=list("abcdef"),
        test_month=np.array([f"2025-{1 + (i % 4):02d}" for i in range(n)]),
        hour=np.full(n, 13.0),
    )


def test_basket_spec_fields():
    spec = basket_spec(horizon=3, k=2, band=0.0, fill_mode="aggressive")
    assert spec.required_fn == "score"
    assert spec.grid_h == [3]
    assert spec.aggregate == "robust"
    assert "reversal" in spec.seed_programs


def test_score_program_runs_end_to_end():
    spec = basket_spec(horizon=3, k=2, band=0.0, fill_mode="aggressive")
    split = _split()
    value, mean, se, logs = score_program(BASKET_SEED_PROGRAMS["reversal"], spec, split)
    assert np.isfinite(value)
    assert value > -1e6, f"program failed to score: {logs}"

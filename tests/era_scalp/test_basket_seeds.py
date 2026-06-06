import numpy as np
from scripts.era_scalp.basket_context import BasketContext
from scripts.era_scalp.basket_sandbox import causality_probe, run_program
from scripts.era_scalp.basket_seeds import BASKET_RESEARCH_IDEAS, BASKET_SEED_PROGRAMS


def _ctx(n=24, m=6, seed=3):
    rng = np.random.default_rng(seed)
    return BasketContext(r=rng.standard_normal((n, m)), names=list("abcdef"), hour=None)


def test_seeds_present():
    assert set(BASKET_SEED_PROGRAMS) == {"reversal", "momentum", "lead_lag"}
    assert len(BASKET_RESEARCH_IDEAS) >= 3


def test_seeds_execute_and_are_causal():
    ctx = _ctx()
    for name, src in BASKET_SEED_PROGRAMS.items():
        out, err, logs = run_program(src, ctx)
        assert err is None, f"{name} exec error: {err}\n{logs}"
        assert out.shape == (ctx.n_bars, ctx.n_sym)
        ok, reason = causality_probe(src, ctx, out)
        assert ok, f"{name} not causal: {reason}"

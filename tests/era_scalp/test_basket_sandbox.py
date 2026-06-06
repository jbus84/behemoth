import numpy as np

from scripts.era_scalp.basket_context import BasketContext
from scripts.era_scalp.basket_sandbox import causality_probe, run_program, static_check

CAUSAL = """
def score(ctx):
    r = ctx.r
    n, m = r.shape
    out = np.full((n, m), np.nan)
    c = np.cumsum(np.nan_to_num(r), axis=0)
    w = 3
    for t in range(n):
        lo = t - w + 1
        if lo < 0:
            continue
        s = c[t] - (c[lo - 1] if lo > 0 else 0.0)
        out[t] = -s
    return out
"""

NONCAUSAL = """
def score(ctx):
    r = ctx.r
    # reads the FULL column (future rows) -> must be rejected
    return -(r - r.mean(axis=0))
"""

BADSHAPE = """
def score(ctx):
    return ctx.r[:, 0]
"""


def _ctx(n=12, m=4, seed=0):
    rng = np.random.default_rng(seed)
    return BasketContext(r=rng.standard_normal((n, m)), names=list("abcd"), hour=None)


def test_static_check_requires_score():
    ok, _ = static_check("def residual(ctx):\n    return ctx.r")
    assert not ok
    ok, _ = static_check(CAUSAL)
    assert ok


def test_run_program_returns_2d():
    ctx = _ctx()
    out, err, _ = run_program(CAUSAL, ctx)
    assert err is None
    assert out.shape == (ctx.n_bars, ctx.n_sym)


def test_run_program_rejects_bad_shape():
    out, err, _ = run_program(BADSHAPE, _ctx())
    assert out is None
    assert err is not None


def test_causality_probe_passes_causal_rejects_noncausal():
    ctx = _ctx()
    out, err, _ = run_program(CAUSAL, ctx)
    assert err is None
    ok, _ = causality_probe(CAUSAL, ctx, out)
    assert ok

    out2, err2, _ = run_program(NONCAUSAL, ctx)
    assert err2 is None
    ok2, _ = causality_probe(NONCAUSAL, ctx, out2)
    assert not ok2

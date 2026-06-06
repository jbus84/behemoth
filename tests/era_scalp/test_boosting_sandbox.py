import numpy as np
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.boosting_sandbox import causality_probe, run_program, static_check

CAUSAL = (
    "def build_features(ctx):\n"
    "    v = np.nan_to_num(ctx.col('vel_pips_h1'))\n"
    "    c = np.cumsum(v)\n"
    "    out = np.full((ctx.n_bars, 1), np.nan)\n"
    "    for t in range(ctx.n_bars):\n"
    "        if t >= 5:\n"
    "            out[t, 0] = c[t] - c[t-5]\n"
    "    return out\n"
)
LEAKY = (
    "def build_features(ctx):\n"
    "    v = ctx.col('vel_pips_h1')\n"
    "    return (v - v.mean()).reshape(-1, 1)\n"  # uses full-column mean = future
)
NOFUNC = "def other(ctx):\n    return ctx.X\n"


def _ctx(n=40, seed=0):
    rng = np.random.default_rng(seed)
    names = ["vel_pips_h1", "range_pips"]
    return FeatureContext(X=rng.standard_normal((n, len(names))), names=names, hour=None)


def test_static_check_requires_build_features():
    assert not static_check(NOFUNC)[0]
    assert static_check(CAUSAL)[0]


def test_run_program_returns_2d_variable_width():
    out, err, _ = run_program(CAUSAL, _ctx())
    assert err is None and out.ndim == 2 and out.shape[0] == 40


def test_causality_probe_accepts_causal_rejects_leaky():
    out, err, _ = run_program(CAUSAL, _ctx())
    assert err is None and causality_probe(CAUSAL, _ctx(), out)[0]
    out2, err2, _ = run_program(LEAKY, _ctx())
    assert err2 is None and not causality_probe(LEAKY, _ctx(), out2)[0]

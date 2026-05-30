import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.sandbox import causality_probe, run_program

NAMES = ["spread_z", "vel_z_h1", "vel_pips_h1", "bar_return_sign", "hour_utc"]


def _ctx(n=120, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(NAMES)))
    return FeatureContext(X=X, names=list(NAMES), hour=(np.arange(n) % 24).astype(float))


CAUSAL = (
    "def signal(ctx):\n"
    "    return ctx.col('vel_z_h1')\n"
)
FORWARD = (
    "def signal(ctx):\n"
    "    x = ctx.col('vel_z_h1').copy()\n"
    "    x[:-1] = (x[:-1] + x[1:]) / 2.0  # reads bar k+1\n"
    "    return x\n"
)


def test_run_program_ok_and_probe_accepts_causal():
    ctx = _ctx()
    sig, err, _ = run_program(CAUSAL, ctx)
    assert err is None and sig.shape == (120,)
    ok, reason = causality_probe(CAUSAL, ctx, sig)
    assert ok, reason


def test_probe_rejects_forward():
    ctx = _ctx()
    sig, err, _ = run_program(FORWARD, ctx)
    assert err is None
    ok, reason = causality_probe(FORWARD, ctx, sig)
    assert not ok and ("future" in reason.lower() or "causal" in reason.lower())


def test_static_check_requires_signal():
    ctx = _ctx()
    _, err, _ = run_program("def residual(ctx):\n    return ctx.col('vel_z_h1')\n", ctx)
    assert err is not None and "signal" in err.lower()

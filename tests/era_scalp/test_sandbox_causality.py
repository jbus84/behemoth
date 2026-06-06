import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS
from scripts.era_scalp.sandbox import causality_probe, run_program

NAMES = ["spread_z", "vel_z_h1", "vel_pips_h1", "bar_return_sign", "hour_utc", "range_pips"]


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


# A program that leaks the NaN-pattern of FUTURE rows into a PAST output.
FINITENESS_LEAK = (
    "def signal(ctx):\n"
    "    x = ctx.col('spread_z')\n"
    "    n = x.shape[0]\n"
    "    out = np.empty(n)\n"
    "    for i in range(n):\n"
    "        out[i] = np.isfinite(x[i + 1:]).sum()  # reads future finiteness\n"
    "    return out\n"
)


def test_probe_rejects_finiteness_leak():
    ctx = _ctx()
    sig, err, _ = run_program(FINITENESS_LEAK, ctx)
    assert err is None
    ok, reason = causality_probe(FINITENESS_LEAK, ctx, sig)
    assert not ok and ("future" in reason.lower() or "causal" in reason.lower())


def test_probe_default_uses_five_cuts():
    import inspect
    sig = inspect.signature(causality_probe)
    assert sig.parameters["n_cuts"].default == 5


CAUSAL_NAN_SAFE = (
    "def signal(ctx):\n"
    "    x = ctx.col('vel_z_h1')\n"
    "    return np.where(np.isfinite(x), x, 0.0)\n"
)


def test_probe_accepts_nan_safe_causal():
    ctx = _ctx()
    sig, err, _ = run_program(CAUSAL_NAN_SAFE, ctx)
    assert err is None
    ok, reason = causality_probe(CAUSAL_NAN_SAFE, ctx, sig)
    assert ok, reason


def test_seed_programs_pass_hardened_probe():
    # Build a full-whitelist context: fade seeds reference many feature columns
    # (e.g. hl_pos_delta_tick, tick_volume), not just the minimal set in NAMES.
    from scripts.era_scalp.load_splits import WHITELIST

    rng = np.random.default_rng(3)
    X = rng.standard_normal((2000, len(WHITELIST)))
    ctx = FeatureContext(X=X, names=list(WHITELIST), hour=(np.arange(2000) % 24).astype(float))
    for name, src in FADE_SEED_PROGRAMS.items():
        sig, err, _ = run_program(src, ctx)
        assert err is None, f"{name}: {err}"
        ok, reason = causality_probe(src, ctx, sig)
        assert ok, f"{name}: {reason}"

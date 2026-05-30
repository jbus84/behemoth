import numpy as np

from scripts.era.context import CrossSectionContext
from scripts.era.sandbox import causality_probe, run_program

NAMES = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]


def _ctx(n=120, seed=0):
    rng = np.random.default_rng(seed)
    r = rng.standard_normal((n, 6))
    hour = (np.arange(n) % 24).astype(float)
    return CrossSectionContext(r=r, names=list(NAMES), target="EURUSD", usd_sign=1, hour=hour)


# A causal per-bar program: residual[k] depends only on bar k.
CAUSAL = (
    "def residual(ctx):\n"
    "    t = ctx.target_col(); p = ctx.peers()\n"
    "    return (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)\n"
)

# A forward-looking program: uses a centered window (reads future rows).
FORWARD = (
    "def residual(ctx):\n"
    "    x = ctx.target_col()\n"
    "    # mean of [k-1, k, k+1] -> reads bar k+1 (future)\n"
    "    out = x.copy()\n"
    "    out[:-1] = (x[:-1] + x[1:]) / 2.0\n"
    "    return out\n"
)


def test_probe_accepts_causal_program():
    ctx = _ctx()
    resid, err, _ = run_program(CAUSAL, ctx)
    assert err is None
    ok, reason = causality_probe(CAUSAL, ctx, resid)
    assert ok, reason


def test_probe_rejects_forward_looking_program():
    ctx = _ctx()
    resid, err, _ = run_program(FORWARD, ctx)
    assert err is None
    ok, reason = causality_probe(FORWARD, ctx, resid)
    assert not ok
    assert "future" in reason.lower() or "causal" in reason.lower()

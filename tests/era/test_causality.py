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


def test_scorer_rejects_noncausal_program():
    from scripts.era.score_program import ProgramScorer, SplitData

    n = 120
    rng = np.random.default_rng(1)
    d = SplitData(
        r=rng.standard_normal((n, 6)),
        names=list(NAMES),
        target="EURUSD",
        usd_sign=1,
        y_fwd=rng.standard_normal(n),
        cost=np.full(n, 0.1),
        test_month=np.array(["2025-07"] * n),
        hour=(np.arange(n) % 24).astype(float),
    )
    scorer = ProgramScorer(splits={"validation": d}, thresholds=[1.0, 1.5])
    score, logs = scorer.score(FORWARD, "validation")
    assert score == -1e6
    assert "causal" in logs.lower()


# A program that leaks the NaN-pattern of FUTURE rows into a PAST output.
FINITENESS_LEAK = (
    "def residual(ctx):\n"
    "    x = ctx.target_col(); n = x.shape[0]\n"
    "    out = np.empty(n)\n"
    "    for i in range(n):\n"
    "        out[i] = np.isfinite(x[i + 1:]).sum()  # reads future finiteness\n"
    "    return out\n"
)


def test_probe_default_uses_five_cuts():
    import inspect

    sig = inspect.signature(causality_probe)
    assert sig.parameters["n_cuts"].default == 5


def test_probe_rejects_finiteness_leak():
    ctx = _ctx()
    resid, err, _ = run_program(FINITENESS_LEAK, ctx)
    assert err is None
    ok, reason = causality_probe(FINITENESS_LEAK, ctx, resid)
    assert not ok and ("future" in reason.lower() or "causal" in reason.lower())


def test_static_check_forbids_np_random():
    from scripts.era.sandbox import static_check

    ok, reason = static_check(
        "def residual(ctx):\n    return np.random.standard_normal(ctx.n_bars)\n"
    )
    assert not ok and "random" in reason.lower()


def test_static_check_accepts_np_without_random():
    from scripts.era.sandbox import static_check

    ok, reason = static_check(
        "def residual(ctx):\n    return ctx.target_col() * 2.0\n"
    )
    assert ok, reason


def test_all_seeds_are_causal():
    from scripts.era.seeds import SEED_PROGRAMS

    ctx = _ctx(n=160, seed=3)
    bad = []
    for name, src in SEED_PROGRAMS.items():
        resid, err, _ = run_program(src, ctx)
        if err is not None:
            bad.append(f"{name}: exec error {err}")
            continue
        ok, reason = causality_probe(src, ctx, resid)
        if not ok:
            bad.append(f"{name}: {reason}")
    assert not bad, "non-causal seeds: " + "; ".join(bad)

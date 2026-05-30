import numpy as np
from scripts.era.context import CrossSectionContext
from scripts.era.sandbox import static_check, run_program

GOOD = """
def residual(ctx):
    import numpy as np  # NOTE: numpy provided in namespace, no import needed
    t = ctx.target_col()
    p = ctx.peers()
    return (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)
"""

CLEAN = """
def residual(ctx):
    t = ctx.target_col(); p = ctx.peers()
    return (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)
"""

def _ctx():
    r = np.random.RandomState(0).randn(20, 6)
    return CrossSectionContext(r=r, names=list("ABCDEF"), target="A", usd_sign=-1)

def test_static_check_rejects_imports_and_dunders():
    ok, reason = static_check("def residual(ctx):\n    import os\n    return ctx.target_col()")
    assert not ok and "import" in reason.lower()
    ok, _ = static_check("def residual(ctx):\n    return ctx.__class__")
    assert not ok
    ok, _ = static_check("def residual(ctx):\n    return open('x')")
    assert not ok

def test_static_check_accepts_clean():
    ok, reason = static_check(CLEAN)
    assert ok, reason

def test_run_clean_program_returns_array():
    res, err, logs = run_program(CLEAN, _ctx(), timeout=10.0)
    assert err is None, err
    assert res.shape == (20,)

def test_run_rejects_bad_program_before_exec():
    res, err, logs = run_program("def residual(ctx):\n    import os\n    return 1", _ctx(), timeout=10.0)
    assert res is None and err is not None

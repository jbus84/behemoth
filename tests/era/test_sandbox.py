import numpy as np

from scripts.era.context import CrossSectionContext
from scripts.era.sandbox import run_program, static_check

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

PROGRAM_WITH_HOUR_GATE = """
def residual(ctx):
    r = ctx.target_col().copy()
    r[ctx.hour >= 6] = np.nan
    return r
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
    res, err, logs = run_program(
        "def residual(ctx):\n    import os\n    return 1", _ctx(), timeout=10.0
    )
    assert res is None and err is not None


def test_run_program_with_hour_gate():
    """Test that a program can use ctx.hour for self-gating."""
    hour = np.array(
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19], dtype=int
    )
    r = np.random.RandomState(0).randn(20, 6)
    ctx = CrossSectionContext(r=r, names=list("ABCDEF"), target="A", usd_sign=-1, hour=hour)
    res, err, logs = run_program(PROGRAM_WITH_HOUR_GATE, ctx, timeout=10.0)
    assert err is None, f"Error: {err}"
    assert res.shape == (20,)
    # Hours 0-5 should have values (not NaN), hours 6-19 should be NaN
    assert not np.any(np.isnan(res[:6])), "First 6 elements (hours 0-5) should not be NaN"
    assert np.all(np.isnan(res[6:])), "Last 14 elements (hours 6-19) should be NaN"


def test_run_program_with_dispersion():
    """Test that a program can use ctx.dispersion()."""
    program_with_dispersion = """
def residual(ctx):
    return ctx.dispersion()
"""
    hour = np.array(
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19], dtype=int
    )
    r = np.random.RandomState(0).randn(20, 6)
    ctx = CrossSectionContext(r=r, names=list("ABCDEF"), target="A", usd_sign=-1, hour=hour)
    res, err, logs = run_program(program_with_dispersion, ctx, timeout=10.0)
    assert err is None, f"Error: {err}"
    assert res.shape == (20,)
    # Compare with the expected dispersion
    expected = ctx.dispersion()
    np.testing.assert_array_almost_equal(res, expected)

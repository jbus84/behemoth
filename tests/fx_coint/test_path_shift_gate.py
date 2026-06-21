import numpy as np

from scripts.fx_coint.path_shift_gate import shift_tests


def test_shift_detects_clear_difference():
    rng = np.random.default_rng(0)
    cond = rng.normal(0.5, 1.0, 800)
    uncond = rng.normal(0.0, 1.0, 800)
    r = shift_tests(cond, uncond, seed=1)
    assert r["ks_p"] < 0.01
    assert r["diff"] > 0.3
    assert r["boot_p"] < 0.05


def test_no_shift_when_same():
    rng = np.random.default_rng(2)
    a = rng.normal(0, 1, 800)
    b = rng.normal(0, 1, 800)
    r = shift_tests(a, b, seed=3)
    assert r["ks_p"] > 0.05
    assert r["boot_p"] > 0.05

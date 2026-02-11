import numpy as np

from behemoth.core.zscore import compute_z_scores


def test_compute_z_scores_zero_std_m5():
    errors = np.zeros(600)
    z = compute_z_scores(errors, window=500)
    assert np.allclose(z, 0.0)


def test_compute_z_scores_zero_std_m15():
    errors = np.zeros(600)
    z = compute_z_scores(errors, window=500)
    assert np.allclose(z, 0.0)


def test_compute_z_scores_nonzero_m5():
    errors = np.arange(600, dtype=float)
    z = compute_z_scores(errors, window=500)
    assert z[500] != 0.0


def test_compute_z_scores_nonzero_m15():
    errors = np.arange(600, dtype=float)
    z = compute_z_scores(errors, window=500)
    assert z[500] != 0.0

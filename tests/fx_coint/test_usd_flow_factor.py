import numpy as np

from scripts.fx_coint.usd_flow_factor import orient, usd_factor_residual


def test_orient_applies_signs():
    flow = np.array([[1.0, 2.0], [3.0, 4.0]])
    signs = np.array([-1.0, 1.0])
    np.testing.assert_allclose(orient(flow, signs), np.array([[-1.0, 2.0], [-3.0, 4.0]]))


def test_factor_is_mean_and_residual_sums_to_zero():
    flow_oriented = np.array([[1.0, 3.0, 2.0], [0.0, 0.0, 6.0]])
    factor, residual = usd_factor_residual(flow_oriented)
    np.testing.assert_allclose(factor, np.array([2.0, 2.0]))
    np.testing.assert_allclose(residual.sum(axis=1), np.zeros(2), atol=1e-12)

import numpy as np

from scripts.fx_coint.reversion_targets import compute_targets


def test_signed_fade_uses_forward_return_against_residual_sign():
    lr = np.array([[np.nan], [0.0010], [-0.0004]])
    residual = np.array([[np.nan], [0.0010], [-0.0004]])
    signed, absm = compute_targets(lr, residual)
    assert np.isclose(signed[1, 0], 4.0)
    assert np.isclose(absm[1, 0], 4.0)
    assert np.isnan(signed[2, 0])

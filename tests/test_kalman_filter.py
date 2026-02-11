import numpy as np

from behemoth.core.kalman import KalmanFilterReg, KalmanFilterRegMulti


def test_kalman_filter_reg_converges():
    kf = KalmanFilterReg()
    # y = 2x
    for x in np.linspace(1.0, 2.0, 50):
        y = 2.0 * x
        beta, _ = kf.update(x, y)
    assert beta > 1.5


def test_kalman_filter_reg_multi_shape_check():
    kf = KalmanFilterRegMulti(k=2)
    try:
        kf.update([1.0], 1.0)
        raise AssertionError("Expected shape error")
    except ValueError:
        assert True


def test_kalman_filter_reg_multi_update():
    kf = KalmanFilterRegMulti(k=2)
    beta, residual = kf.update([1.0, 0.5], 2.0)
    assert len(beta) == 2
    assert isinstance(residual, float)


def test_kalman_filter_reg_multi_zero_innovation():
    kf = KalmanFilterRegMulti(k=1, R=0.0, Q=0.0)
    beta, residual = kf.update([0.0], 0.0)
    assert beta.shape == (1,)
    assert residual == 0.0

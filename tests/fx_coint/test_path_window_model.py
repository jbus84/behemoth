import numpy as np
import pytest

from scripts.fx_coint.path_window_model import (
    build_window_matrix,
    path_channels,
)


def test_path_channels_order_and_shape():
    n = 50
    logp = np.cumsum(np.ones(n) * 0.001)
    vol = np.full(n, 0.002)
    f = {"intra_bar_mom": np.arange(n, dtype=float),
         "hl_pos_frac": np.linspace(0, 1, n)}
    chans = path_channels(logp, f, vol)
    assert len(chans) == 4
    assert all(c.shape == (n,) for c in chans)
    assert chans[0][0] == 0.0
    np.testing.assert_allclose(chans[0][1:], np.diff(logp))
    np.testing.assert_array_equal(chans[2], np.arange(n, dtype=float))


def test_build_window_matrix_shape_and_content():
    n, W = 20, 4
    ch0 = np.arange(n, dtype=float)
    ch1 = np.arange(n, dtype=float) * 10
    channels = [ch0, ch1]  # C=2
    entry = np.array([5, 10])
    X = build_window_matrix(channels, entry, W)
    assert X.shape == (2, W * 2)
    np.testing.assert_array_equal(X[0], np.array([2, 3, 4, 5, 20, 30, 40, 50], dtype=float))


def test_build_window_matrix_rejects_short_entry():
    channels = [np.arange(20, dtype=float)]
    with pytest.raises(ValueError):
        build_window_matrix(channels, np.array([2]), W=4)

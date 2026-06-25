import numpy as np
import pytest

from scripts.fx_coint.path_window_model import (
    POOL,
    build_sym_window,
    build_window_matrix,
    path_channels,
    sample_events,
)


def _fake_cache(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    logp = np.cumsum(rng.standard_normal(n) * 0.001)
    vol = np.full(n, 0.002)
    f = {"intra_bar_mom": rng.standard_normal(n),
         "hl_pos_frac": rng.random(n)}
    bph = 12.0
    return logp, f, vol, bph


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
    channels = [ch0, ch1]
    entry = np.array([5, 10])
    X = build_window_matrix(channels, entry, W)
    assert X.shape == (2, W * 2)
    np.testing.assert_array_equal(X[0], np.array([2, 3, 4, 5, 20, 30, 40, 50], dtype=float))


def test_build_window_matrix_rejects_short_entry():
    channels = [np.arange(20, dtype=float)]
    with pytest.raises(ValueError):
        build_window_matrix(channels, np.array([2]), W=4)


def test_sample_events_respects_window_floor():
    cache = {s: _fake_cache(seed=i) for i, s in enumerate(POOL[:1])}
    rng = np.random.default_rng(0)
    ev = sample_events(cache, n_tb=50, W_max=64, rng=rng)
    s = POOL[0]
    assert ev[s].min() >= 64 - 1
    assert np.all(np.diff(ev[s]) > 0)


def test_build_sym_window_shapes_align():
    cache = {s: _fake_cache(seed=i) for i, s in enumerate(POOL[:1])}
    rng = np.random.default_rng(0)
    ev = sample_events(cache, n_tb=30, W_max=32, rng=rng)
    sym_data = build_sym_window(cache, ev, n_tb=30, W=32)
    s = POOL[0]
    d = sym_data[s]
    assert d["X"].shape[1] == 32 * 4
    assert d["X"].shape[0] == d["entry"].shape[0] == d["ret"].shape[0]
    assert np.isfinite(d["X"]).all()

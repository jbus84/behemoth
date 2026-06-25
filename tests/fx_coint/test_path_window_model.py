import numpy as np

from scripts.fx_coint.path_window_model import POOL, build_sym_window, sample_events


def _fake_cache(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    logp = np.cumsum(rng.standard_normal(n) * 0.001)
    vol = np.full(n, 0.002)
    f = {"intra_bar_mom": rng.standard_normal(n),
         "hl_pos_frac": rng.random(n)}
    bph = 12.0
    return logp, f, vol, bph


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

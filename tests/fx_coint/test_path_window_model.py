import numpy as np
import pytest

from scripts.fx_coint.path_window_model import (
    POOL,
    build_sym_window,
    build_window_matrix,
    evaluate_cell,
    fit_predict_for,
    make_window_models,
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


def test_evaluate_cell_structure_on_synthetic():
    rng = np.random.default_rng(0)
    sym_data = {}
    for s in ["A", "B"]:
        n = 1200
        entry = np.sort(rng.choice(np.arange(100, 5000), n, replace=False))
        X = rng.standard_normal((n, 8))
        ret = X[:, 0] * 0.001 + rng.standard_normal(n) * 0.0005
        sym_data[s] = dict(X=X, y=ret, entry=entry, t1=entry + 1,
                           ret=ret, sw=np.ones(n))
    model = make_window_models(seed=0)["histgbm"]
    out = evaluate_cell(sym_data, model, cost_by_sym={"A": 0.0, "B": 0.0}, n_folds=4)
    assert set(out) == {"pooled", "per_symbol"}
    assert set(out["per_symbol"]) == {"A", "B"}
    for v in [out["pooled"], *out["per_symbol"].values()]:
        assert {"net", "lo", "hi", "p_neg", "folds_pos", "n_trades"} <= set(v)


def test_window_models_learn_linear_signal():
    rng = np.random.default_rng(0)
    n, p = 4000, 16
    X = rng.standard_normal((n, p))
    beta = np.zeros(p)
    beta[0] = 2.0
    y = X @ beta + rng.standard_normal(n) * 0.1
    cut = 3200
    train = {"X": X[:cut], "y": y[:cut], "sw": np.ones(cut)}
    test = {"X": X[cut:], "y": y[cut:], "sw": np.ones(n - cut)}
    models = make_window_models(seed=0)
    for name, model in models.items():
        mu = fit_predict_for(model)(train, test)
        corr = np.corrcoef(mu, test["X"][:, 0])[0, 1]
        assert corr > 0.5, f"{name} corr={corr:.2f}"

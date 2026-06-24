import numpy as np
from scipy.stats import spearmanr

from scripts.fx_coint.model_search import build_design, make_models


def test_build_design_adds_interaction_columns():
    f = {"a": np.array([1.0, 2.0, 3.0]), "b": np.array([10.0, 20.0, 30.0])}
    ev = np.array([0, 1, 2])
    X, names = build_design(f, ev, ["a", "b"], [("a", "b")])
    assert X.shape == (3, 3)
    assert names == ["a", "b", "a*b"]
    assert np.allclose(X[:, 2], [10.0, 40.0, 90.0])   # a*b


def test_models_fit_predict_learnable_signal():
    rng = np.random.default_rng(0)
    n = 10000
    X = rng.standard_normal((n, 3))
    y = X[:, 0] * 1.2 + 0.3 * rng.standard_normal(n)
    for name, m in make_models().items():
        m.fit(X, y)
        pred = m.predict(X)
        assert spearmanr(pred, y)[0] > 0.4, name

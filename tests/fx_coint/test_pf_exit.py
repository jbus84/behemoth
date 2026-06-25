import numpy as np

from scripts.fx_coint.pf_exit import exit_index


def _post(p_trend, mu_hat):
    n = len(p_trend)
    return {"p_trend": np.array(p_trend), "mu_hat": np.array(mu_hat),
            "mu_var": np.ones(n)}

def test_exit_on_regime_collapse():
    post = _post([0.9, 0.9, 0.2, 0.9], [1.0, 1.0, 1.0, 1.0])
    assert exit_index(post, side="long", max_hold=4) == 2

def test_exit_on_drift_flip_long():
    post = _post([0.9, 0.9, 0.9, 0.9], [1.0, 0.5, -0.3, 1.0])
    assert exit_index(post, side="long", max_hold=4) == 2

def test_no_trigger_holds_to_cap():
    post = _post([0.9, 0.9, 0.9], [1.0, 1.0, 1.0])
    assert exit_index(post, side="long", max_hold=3) == 2

def test_short_side_flip():
    post = _post([0.9, 0.9, 0.9], [-1.0, 0.4, -1.0])
    assert exit_index(post, side="short", max_hold=3) == 1

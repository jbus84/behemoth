"""Tests for nbar_model_directional."""
import numpy as np
import pytest

from scripts.fx_coint.nbar_model_directional import evaluate_directional


def test_evaluate_directional_perfect_signal():
    """Perfect directional predictor should show high net."""
    n = 200
    sym_data = {
        "S": dict(
            entry=np.arange(n),
            t1=np.arange(n) + 1,
            ret=np.ones(n),          # always +1 bps
        )
    }
    # predict +1 always -> sign(mu)=+1 -> position=+1 -> ret=+1 -> net=0 (cost=1)
    preds = {"S": np.ones(n)}
    out = evaluate_directional(sym_data, preds, cost=1.0, n_folds=4, q=0.0)
    assert out["n_trades"] > 0
    assert out["net"] == pytest.approx(0.0, abs=1e-9)  # +1 - 1 = 0


def test_evaluate_directional_anti_predictor():
    """Always-wrong predictor should show negative net."""
    n = 200
    sym_data = {
        "S": dict(
            entry=np.arange(n),
            t1=np.arange(n) + 1,
            ret=np.ones(n),          # always +1 bps
        )
    }
    # predict -1 always -> sign(mu)=-1 -> position=-1 -> ret=-1 -> net=-2
    preds = {"S": -np.ones(n)}
    out = evaluate_directional(sym_data, preds, cost=1.0, n_folds=4, q=0.0)
    assert out["net"] == pytest.approx(-2.0, abs=1e-9)

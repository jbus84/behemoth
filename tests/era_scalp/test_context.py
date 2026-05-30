import numpy as np

from scripts.era_scalp.context import FeatureContext

NAMES = ["spread_z", "vel_z_h1", "bar_return_sign", "hour_utc"]


def _ctx(n=50):
    X = np.arange(n * len(NAMES), dtype=float).reshape(n, len(NAMES))
    hour = (np.arange(n) % 24).astype(float)
    return FeatureContext(X=X, names=list(NAMES), hour=hour)


def test_feature_context_accessors():
    ctx = _ctx()
    assert ctx.n_bars == 50
    assert ctx.names == NAMES
    np.testing.assert_array_equal(ctx.col("vel_z_h1"), ctx.X[:, 1])
    assert ctx.col("hour_utc").shape == (50,)


def test_col_unknown_raises():
    ctx = _ctx()
    try:
        ctx.col("does_not_exist")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass

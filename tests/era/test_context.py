import numpy as np

from scripts.era.context import CrossSectionContext


def _ctx():
    r = np.arange(12, dtype=float).reshape(4, 3)  # 4 bars, 3 symbols (test size)
    return CrossSectionContext(
        r=r, names=["EURUSD", "GBPUSD", "USDJPY"], target="EURUSD", usd_sign=-1
    )


def test_target_index_and_peers():
    ctx = _ctx()
    assert ctx.target_idx == 0
    assert ctx.n_bars == 4
    assert ctx.peer_idx == [1, 2]
    # target column view
    np.testing.assert_array_equal(ctx.target_col(), np.array([0.0, 3.0, 6.0, 9.0]))
    # peers matrix is (n_bars, n_peers)
    assert ctx.peers().shape == (4, 2)


def test_no_future_attributes():
    ctx = _ctx()
    for bad in ("y_fwd", "y_fwd_pips", "future", "label", "target_gross"):
        assert not hasattr(ctx, bad)


def test_dispersion():
    """Test that dispersion() returns per-bar cross-sectional std."""
    r = np.array(
        [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]], dtype=float
    )  # 3 bars, 3 symbols
    ctx = CrossSectionContext(r=r, names=["A", "B", "C"], target="A", usd_sign=1)
    disp = ctx.dispersion()
    expected = r.std(axis=1)
    np.testing.assert_array_almost_equal(disp, expected)
    assert disp.shape == (3,)


def test_hour_optional_field():
    """Test that hour field is optional and can be set."""
    r = np.arange(12, dtype=float).reshape(4, 3)
    hour = np.array([0, 5, 10, 15], dtype=int)
    ctx = CrossSectionContext(
        r=r, names=["EURUSD", "GBPUSD", "USDJPY"], target="EURUSD", usd_sign=-1, hour=hour
    )
    np.testing.assert_array_equal(ctx.hour, hour)
    assert ctx.hour.shape == (4,)


def test_hour_default_none():
    """Test that hour defaults to None for backward compatibility."""
    r = np.arange(12, dtype=float).reshape(4, 3)
    ctx = CrossSectionContext(
        r=r, names=["EURUSD", "GBPUSD", "USDJPY"], target="EURUSD", usd_sign=-1
    )
    assert ctx.hour is None

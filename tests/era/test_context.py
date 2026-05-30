import numpy as np
from scripts.era.context import CrossSectionContext

def _ctx():
    r = np.arange(12, dtype=float).reshape(4, 3)  # 4 bars, 3 symbols (test size)
    return CrossSectionContext(r=r, names=["EURUSD", "GBPUSD", "USDJPY"],
                               target="EURUSD", usd_sign=-1)

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

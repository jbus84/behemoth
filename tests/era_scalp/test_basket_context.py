import numpy as np

from scripts.era_scalp.basket_context import BasketContext, BasketSplit


def test_context_shape_and_dispersion():
    r = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    ctx = BasketContext(r=r, names=["a", "b", "c"], hour=None)
    assert ctx.n_bars == 2
    assert ctx.n_sym == 3
    assert np.allclose(ctx.dispersion(), r.std(axis=1))


def test_split_carries_panels():
    n, m = 4, 3
    split = BasketSplit(
        r=np.zeros((n, m)),
        y_fwd_panel=np.ones((n, m)),
        cost_panel=np.full((n, m), 0.5),
        names=["a", "b", "c"],
        test_month=np.array(["2025-01"] * n),
        hour=np.zeros(n),
    )
    assert split.r.shape == (n, m)
    assert split.y_fwd_panel.shape == (n, m)
    assert split.cost_panel.shape == (n, m)
    assert len(split.test_month) == n

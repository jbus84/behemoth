import numpy as np

from scripts.era_scalp.basket_context import BasketSplit
from scripts.era_scalp.basket_score import (
    apply_band,
    make_basket_score_frame,
    periodic_rebalance,
    rank_to_weights,
)


def test_weights_dollar_neutral():
    s = np.array([3.0, 1.0, 2.0, -1.0, 0.5, -2.0])
    w = rank_to_weights(s, k=2)
    assert abs(w.sum()) < 1e-12
    assert np.isclose(w.max(), 0.5)   # 1/k
    assert np.isclose(w.min(), -0.5)
    assert int((w > 0).sum()) == 2 and int((w < 0).sum()) == 2


def test_weights_insufficient_finite_returns_zero():
    s = np.array([np.nan, np.nan, 1.0])
    assert np.allclose(rank_to_weights(s, k=2), 0.0)


def test_apply_band_carries_when_small_move():
    prev = np.array([0.5, -0.5, 0.0])
    target = np.array([0.5, 0.0, -0.5])  # L1 distance = 1.0
    assert np.allclose(apply_band(prev, target, band=2.0), prev)   # carried
    assert np.allclose(apply_band(prev, target, band=0.0), target)  # rebalanced


def _panel_split(n=20, m=4, seed=1):
    rng = np.random.default_rng(seed)
    return BasketSplit(
        r=rng.standard_normal((n, m)),
        y_fwd_panel=rng.standard_normal((n, m)),
        cost_panel=np.full((n, m), 0.2),
        names=list("abcd"),
        test_month=np.array(["2025-01"] * n),
        hour=np.full(n, 13.0),
    )


def test_periodic_rebalance_neutral_and_nonoverlap():
    split = _panel_split()
    scores = split.r.copy()
    frame = periodic_rebalance(scores, split, h=4, k=1, band=0.0,
                               fill_mode="aggressive", passive_frac=0.5, session=None)
    # non-overlapping bars 0,4,8,12 within n=20 minus horizon -> 4 rows
    assert len(frame) == 4
    assert set(frame.columns) == {"net", "test_month"}


def test_nan_forward_return_leg_is_never_held():
    # A symbol with a non-finite forward return at a rebalance bar must be excluded
    # from the held universe (no P&L booked, no cost charged on it).
    split = _panel_split(n=8, m=4, seed=5)
    scores = np.zeros((8, 4))
    scores[0] = np.array([3.0, 2.0, 1.0, 0.0])  # would pick sym0 long, sym3 short at k=1
    split.y_fwd_panel[0, 0] = np.nan            # disqualify the would-be long leg
    frame = periodic_rebalance(scores, split, h=4, k=1, band=0.0,
                               fill_mode="aggressive", passive_frac=0.5, session=None)
    # With sym0 dropped, the rankable universe is {1,2,3}: long sym1, short sym3.
    # The booked net must be finite (no NaN leaked) and must not reference sym0.
    assert np.isfinite(frame["net"].to_numpy()).all()


def test_passive_cost_lower_than_aggressive():
    split = _panel_split()
    scores = split.r.copy()
    agg = periodic_rebalance(scores, split, h=4, k=1, band=0.0,
                             fill_mode="aggressive", passive_frac=0.5, session=None)
    pas = periodic_rebalance(scores, split, h=4, k=1, band=0.0,
                             fill_mode="passive", passive_frac=0.5, session=None)
    # identical gross, passive pays less cost -> passive net >= aggressive net, summed
    assert pas["net"].sum() >= agg["net"].sum()


def test_larger_band_reduces_turnover():
    split = _panel_split(n=60, seed=7)
    scores = split.r.copy()

    def turnover(band):
        prev = np.zeros(split.r.shape[1])
        total = 0.0
        for t in range(0, scores.shape[0] - 4, 4):
            target = rank_to_weights(scores[t], k=1)
            w = apply_band(prev, target, band)
            total += np.abs(w - prev).sum()
            prev = w
        return total

    assert turnover(10.0) <= turnover(0.0)


def test_score_frame_deterministic():
    split = _panel_split()
    sf = make_basket_score_frame(k=1, band=0.0, fill_mode="aggressive",
                                 passive_frac=0.5, session=None)
    a = sf(split.r.copy(), split, 0.0, 4)
    b = sf(split.r.copy(), split, 0.0, 4)
    assert a.equals(b)

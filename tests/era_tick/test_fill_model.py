from __future__ import annotations

from scripts.era_tick.fill_model import FillModel
from scripts.era_tick.tick_replay import Tick


def _tick(bid=1.10000, ask=1.10020):  # 2-pip spread
    return Tick(i=0, ts=None, bid=bid, ask=ask, dt=0.0)


def test_taker_crosses_the_spread():
    fm = FillModel(pip=1e-4)
    t = _tick()
    assert fm.buy_price(t) == t.ask
    assert fm.sell_price(t) == t.bid
    assert abs(fm.round_trip_cost_pips(t) - 2.0) < 1e-9


def test_round_trip_pays_spread_plus_markup():
    pip = 1e-4
    fm = FillModel(pip=pip, retail_markup_pips=0.5)
    t = _tick()  # 2 pip raw spread
    # A long: buy at ask+0.25p, sell at bid-0.25p. Cost = (buy - sell) in pips.
    cost = (fm.buy_price(t) - fm.sell_price(t)) / pip
    assert abs(cost - (2.0 + 0.5)) < 1e-9
    assert abs(fm.round_trip_cost_pips(t) - 2.5) < 1e-9


def test_maker_pays_no_spread_but_is_off_by_default():
    assert FillModel(pip=1e-4).maker is False
    fm = FillModel(pip=1e-4, maker=True)
    t = _tick()
    assert fm.round_trip_cost_pips(t) == 0.0
    assert fm.buy_price(t) == t.bid  # near touch
    assert fm.sell_price(t) == t.ask

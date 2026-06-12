from __future__ import annotations

import numpy as np

from tests.era_tick._synthetic import make_frame, ramp


def test_iterates_in_order_with_dt_and_quotes():
    mids = ramp(n=50)
    from scripts.era_tick.tick_replay import TickReplay

    replay = TickReplay("EURUSD", make_frame(mids, spread_pips=0.2))
    ticks = list(replay)

    assert len(ticks) == 50
    assert [t.i for t in ticks] == list(range(50))
    # monotonic timestamps
    assert all(b.ts > a.ts for a, b in zip(ticks, ticks[1:]))
    # first dt is 0, subsequent are the 100ms cadence
    assert ticks[0].dt == 0.0
    assert all(abs(t.dt - 0.1) < 1e-6 for t in ticks[1:])
    # mid/spread derived from bid/ask
    t0 = ticks[0]
    assert abs(t0.mid - 0.5 * (t0.bid + t0.ask)) < 1e-12
    assert abs(t0.spread - (t0.ask - t0.bid)) < 1e-12
    assert abs(t0.spread / replay.pip - 0.2) < 1e-9


def test_spread_pips_series_matches_pip():
    replay = TickReplay_helper()
    assert np.allclose(replay.spread_pips_series.to_numpy(), 0.2, atol=1e-9)


def TickReplay_helper():
    from scripts.era_tick.tick_replay import TickReplay

    return TickReplay("EURUSD", make_frame(ramp(n=10), spread_pips=0.2))

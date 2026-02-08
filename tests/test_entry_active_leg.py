import numpy as np
import pandas as pd

import wfo_mom_full_params as wfo_m15
import wfo_mom_full_params_m5 as wfo_m5


def _make_pair_state():
    n = 600
    # y rises, x falls to make active-leg choice observable
    y = np.linspace(0.0, 10.0, n)
    x = np.linspace(0.0, -10.0, n)
    ts = pd.date_range("2020-01-01", periods=n, freq="15min", tz="UTC").astype("int64").to_numpy()

    betas = np.ones(n)
    z = np.zeros(n)

    # Entry 1: beta < 0.98 -> active Y, z positive
    betas[510] = 0.97
    z[510] = 1.5
    z[511] = -0.1  # exit via Z cross

    # Entry 2 within min-gap -> should be skipped
    betas[520] = 0.97
    z[520] = 1.5
    z[521] = -0.1

    # Entry 3: beta > 1.02 -> active X, z negative
    betas[535] = 1.03
    z[535] = -1.5
    z[536] = 0.1  # exit via Z cross

    # Neutral zone entry -> should be skipped
    betas[550] = 1.0
    z[550] = 1.5
    z[551] = -0.1

    state = {
        "name": "TEST",
        "y": y,
        "x": x,
        "ts": ts,
        "betas": betas,
        "z_map": {5: z},
    }
    return [state]


def _run(module):
    pair_states = _make_pair_state()
    trades = module._build_trades(pair_states, z_entry=1.5, z_stop=4.0, z_lookback=5)
    return trades


def test_active_leg_and_entry_gating_m15():
    trades = _run(wfo_m15)
    # Expect 2 trades: index 510 and 535
    assert len(trades) == 2
    # Trade 1 should be positive (active Y on rising y)
    assert trades[0]["pnl"] > 0
    # Trade 2 should be positive (active X short on falling x)
    assert trades[1]["pnl"] > 0


def test_active_leg_and_entry_gating_m5():
    trades = _run(wfo_m5)
    assert len(trades) == 2
    assert trades[0]["pnl"] > 0
    assert trades[1]["pnl"] > 0

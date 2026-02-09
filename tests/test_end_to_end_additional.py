import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))

import wfo_mom_full_params as wfo


def _state_for_neutral_and_min_gap():
    n = 600
    y = np.linspace(0.0, 10.0, n)
    x = np.zeros(n)
    ts = pd.date_range("2020-01-01", periods=n, freq="15min", tz="UTC").astype("int64").to_numpy()

    betas = np.ones(n)  # neutral zone
    z = np.zeros(n)

    # Neutral-zone entry candidate -> should be skipped
    z[510] = 1.5
    z[511] = -0.1

    # Now force active leg and two entries inside min gap
    betas[530] = 0.97
    z[530] = 1.5
    z[531] = -0.1

    betas[545] = 0.97
    z[545] = 1.5
    z[546] = -0.1

    state = {
        "name": "TEST",
        "y": y,
        "x": x,
        "ts": ts,
        "betas": betas,
        "z_map": {5: z},
    }
    return [state]


def test_neutral_zone_and_min_gap():
    trades = wfo._build_trades(_state_for_neutral_and_min_gap(), z_entry=1.5, z_stop=4.0, z_lookback=5)
    # Neutral zone skipped, second entry within min-gap skipped
    assert len(trades) == 1


def _state_for_win_loss_mix():
    n = 600
    y = np.linspace(0.0, 10.0, n)
    x = np.zeros(n)
    ts = pd.date_range("2020-01-01", periods=n, freq="15min", tz="UTC").astype("int64").to_numpy()

    betas = np.full(n, 0.97)
    z = np.zeros(n)

    # Trade 1: z positive -> long, y rising -> WIN
    z[510] = 1.5
    z[511] = -0.1  # exit via Z cross

    # Trade 2: z negative -> short, y rising -> LOSS
    z[535] = -1.5
    z[536] = 0.1

    state = {
        "name": "TEST",
        "y": y,
        "x": x,
        "ts": ts,
        "betas": betas,
        "z_map": {5: z},
    }
    return [state]


def test_end_to_end_win_loss_mix():
    trades = wfo._build_trades(_state_for_win_loss_mix(), z_entry=1.5, z_stop=4.0, z_lookback=5)
    assert len(trades) == 2
    assert trades[0]["pnl"] > 0
    assert trades[1]["pnl"] < 0

import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))

import wfo_mom_full_params as wfo


def _make_pair_state():
    n = 700
    y = np.linspace(0.0, 10.0, n)
    x = np.zeros(n)
    ts = pd.date_range("2020-01-01", periods=n, freq="15min", tz="UTC").astype("int64").to_numpy()

    betas = np.full(n, 0.97)  # active leg Y
    z = np.zeros(n)

    # Four MOM entries (shorts) -> all losses since y is rising.
    entries = [510, 531, 552, 573]
    for idx in entries:
        z[idx] = -1.5
        z[idx + 1] = 0.1  # exit via Z cross

    state = {
        "name": "TEST",
        "y": y,
        "x": x,
        "ts": ts,
        "betas": betas,
        "z_map": {5: z},
    }
    return [state]


def test_end_to_end_guardrail_m15():
    pair_states = _make_pair_state()
    trades = wfo._build_trades(pair_states, z_entry=1.5, z_stop=4.0, z_lookback=5)
    assert len(trades) == 4

    train_years = {t["year"] for t in trades}
    kept_train, _ = wfo._apply_loss_streak(trades, 3, 7, train_years, set())

    # After 3 consecutive losses, 4th trade should be skipped by cooldown
    assert len(kept_train) == 3

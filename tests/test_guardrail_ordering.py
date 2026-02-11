import numpy as np
import pandas as pd
import wfo_mom_full_params as wfo


def test_trades_sorted_by_exit_ts():
    # Create synthetic pair state where a later entry exits earlier
    n = 600
    y = np.linspace(0.0, 10.0, n)
    x = np.linspace(0.0, 0.0, n)
    ts = pd.date_range("2020-01-01", periods=n, freq="15min", tz="UTC").astype("int64").to_numpy()

    betas = np.full(n, 0.97)
    z = np.zeros(n)

    # Entry A at 510 exits late at 560
    z[510] = 1.5
    z[560] = -0.1

    # Entry B at 535 exits early at 536
    z[535] = 1.5
    z[536] = -0.1

    state = {
        "name": "TEST",
        "y": y,
        "x": x,
        "ts": ts,
        "betas": betas,
        "z_map": {5: z},
    }

    trades = wfo._build_trades([state], z_entry=1.5, z_stop=4.0, z_lookback=5)
    exit_ts = np.array([t["exit_ts"] for t in trades])

    # Trades should be sorted by exit time
    assert np.all(exit_ts[:-1] <= exit_ts[1:])

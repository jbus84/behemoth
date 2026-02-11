import numpy as np
import pandas as pd
import wfo_mom_full_params as wfo

from behemoth.core.events import simulate_trade
from behemoth.core.zscore import compute_z_scores


def test_compute_z_scores_causal():
    errors = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    z = compute_z_scores(errors, window=3)
    # First z is at index 3 using window [1,2,3]
    mu = np.mean(errors[0:3])
    std = np.std(errors[0:3])
    expected = (errors[3] - mu) / std
    assert np.isclose(z[3], expected, atol=1e-9)
    # Ensure no z computed before window
    assert z[0] == 0.0
    assert z[1] == 0.0
    assert z[2] == 0.0


def test_mom_exit_cross_zero_long():
    y = np.array([0.0, 1.0, 2.0, 3.0])
    x = np.array([0.0, 0.0, 0.0, 0.0])
    z_scores = np.array([0.0, 1.6, -0.1, 0.0])
    pnl, duration, label = simulate_trade(
        entry_idx=1,
        direction=1,
        strategy_type="MOM",
        y=y,
        x=x,
        z_scores=z_scores,
        active_asset="Y",
        thresh=1.5,
        stop=4.0,
    )
    assert label == "LOSS_REV"
    assert duration == 1
    assert pnl == 10000.0


def test_mom_exit_stop_short():
    y = np.array([0.0, -1.0, -2.0, -3.0])
    x = np.array([0.0, 0.0, 0.0, 0.0])
    z_scores = np.array([0.0, -1.6, -4.1, -4.2])
    pnl, duration, label = simulate_trade(
        entry_idx=1,
        direction=-1,
        strategy_type="MOM",
        y=y,
        x=x,
        z_scores=z_scores,
        active_asset="Y",
        thresh=1.5,
        stop=4.0,
    )
    assert label == "WIN_MOM"
    assert duration == 1
    assert pnl == 10000.0


def test_timeout_exit():
    n = 505
    y = np.linspace(0.0, 1.0, n)
    x = np.zeros(n)
    z_scores = np.full(n, 2.0)  # never crosses 0 or stop=4.0
    pnl, duration, label = simulate_trade(
        entry_idx=1,
        direction=1,
        strategy_type="MOM",
        y=y,
        x=x,
        z_scores=z_scores,
        active_asset="Y",
        thresh=1.5,
        stop=4.0,
    )
    assert label == "TIMEOUT"
    assert duration == 500
    # Exit at entry+499 index
    exit_idx = 1 + 499
    expected = (y[exit_idx] - y[1]) * 10000
    assert np.isclose(pnl, expected)


def test_guardrail_loss_streak_pause():
    base = pd.Timestamp("2020-01-01", tz="UTC").value
    day = int(pd.Timedelta(days=1).value)

    trades = [
        {"pair": "X", "exit_ts": base + 0 * day, "pnl": -1.0, "year": 2020},
        {"pair": "X", "exit_ts": base + 1 * day, "pnl": -1.0, "year": 2020},
        {"pair": "X", "exit_ts": base + 2 * day, "pnl": -1.0, "year": 2020},
        {"pair": "X", "exit_ts": base + 3 * day, "pnl": -1.0, "year": 2020},
        {"pair": "X", "exit_ts": base + 12 * day, "pnl": 1.0, "year": 2020},
    ]

    train_years = {2020}
    test_years = set()
    kept_train, _ = wfo._apply_loss_streak(trades, 3, 7, train_years, test_years)

    # First 3 losses kept, 4th loss skipped due to cooldown, 5th kept
    assert len(kept_train) == 4

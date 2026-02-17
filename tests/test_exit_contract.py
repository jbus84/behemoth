import numpy as np

from behemoth.core.events import simulate_trade
from behemoth.core.exit_contract import build_exit_contract
from behemoth.core.timeout_policy import compute_max_hold_bars


def test_compute_max_hold_bars_adaptive_m15_boundaries():
    assert compute_max_hold_bars("m15", 1.5, mode="adaptive_entry_z") == 120
    assert compute_max_hold_bars("m15", 2.0, mode="adaptive_entry_z") == 180
    assert compute_max_hold_bars("m15", 2.5, mode="adaptive_entry_z") == 260
    assert compute_max_hold_bars("m15", 3.0, mode="adaptive_entry_z") == 400


def test_simulate_trade_respects_entry_time_max_hold():
    y = np.array([1.0, 1.001, 1.002, 1.003, 1.004, 1.005])
    x = np.array([1.0] * len(y))
    z = np.array([2.0] + [1.0] * (len(y) - 1))
    contract = build_exit_contract(
        timeframe="m15",
        entry_z=2.2,
        timeout_mode="adaptive_entry_z",
        variant="baseline",
        z_stop=4.0,
    )
    pnl, duration, outcome = simulate_trade(
        0,
        1,
        "MOM",
        y,
        x,
        z,
        "Y",
        stop=4.0,
        exit_contract=contract,
    )
    assert outcome == "TIMEOUT"
    assert duration == contract.max_hold_bars


def test_soft_cross_uses_entry_time_buffer():
    y = np.array([1.0, 1.01, 1.02, 1.03])
    x = np.array([1.0, 1.0, 1.0, 1.0])
    z = np.array([2.0, -0.05, -0.20, -0.30])
    contract = build_exit_contract(
        timeframe="m15",
        entry_z=2.0,
        timeout_mode="fixed",
        variant="soft_cross",
        z_stop=4.0,
    )
    _, duration, outcome = simulate_trade(
        0,
        1,
        "MOM",
        y,
        x,
        z,
        "Y",
        stop=4.0,
        exit_contract=contract,
    )
    # Should not exit at z=-0.05, should exit once below -0.15 buffer.
    assert outcome == "LOSS_REV"
    assert duration == 2


def test_no_stop_win_disables_stop_exit():
    y = np.array([1.0, 1.01, 1.02, 1.03])
    x = np.array([1.0, 1.0, 1.0, 1.0])
    z = np.array([2.0, 4.5, 4.6, 4.7])
    contract = build_exit_contract(
        timeframe="m15",
        entry_z=2.0,
        timeout_mode="fixed",
        variant="no_stop_win",
        z_stop=4.0,
    )
    _, duration, outcome = simulate_trade(
        0,
        1,
        "MOM",
        y,
        x,
        z,
        "Y",
        stop=4.0,
        exit_contract=contract,
    )
    assert outcome == "TIMEOUT"
    assert duration == 500

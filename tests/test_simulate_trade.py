import os
import sys

import numpy as np

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3_m5 as m5
import build_meta_dataset_v3 as m15


def test_simulate_trade_mom_long_loss_rev_m5():
    y = np.array([1.0, 1.01])
    x = np.array([1.0, 1.0])
    z = np.array([2.0, -0.5])
    pnl, dur, outcome = m5.simulate_trade(0, 1, "MOM", y, x, z, "Y", stop=3.5)
    assert outcome == "LOSS_REV"
    assert dur == 1


def test_simulate_trade_rev_win_m15():
    y = np.array([1.0, 1.01])
    x = np.array([1.0, 1.0])
    z = np.array([-2.0, 0.5])
    pnl, dur, outcome = m15.simulate_trade(0, 1, "REV", y, x, z, "Y", stop=3.5)
    assert outcome == "WIN_REV"
    assert dur == 1


def test_simulate_trade_mom_win_stop_m5():
    y = np.array([1.0, 1.02])
    x = np.array([1.0, 1.0])
    z = np.array([2.0, 4.1])
    pnl, dur, outcome = m5.simulate_trade(0, 1, "MOM", y, x, z, "Y", stop=3.5)
    assert outcome == "WIN_MOM"
    assert dur == 1


def test_simulate_trade_rev_loss_stop_m15():
    y = np.array([1.0, 0.98])
    x = np.array([1.0, 1.0])
    z = np.array([-2.0, -4.1])
    pnl, dur, outcome = m15.simulate_trade(0, 1, "REV", y, x, z, "Y", stop=3.5)
    assert outcome == "LOSS_MOM"
    assert dur == 1


def test_simulate_trade_mom_short_loss_rev_m15():
    y = np.array([1.0, 1.01])
    x = np.array([1.0, 1.0])
    z = np.array([-2.0, 0.5])
    pnl, dur, outcome = m15.simulate_trade(0, -1, "MOM", y, x, z, "Y", stop=3.5)
    assert outcome == "LOSS_REV"
    assert dur == 1


def test_simulate_trade_mom_short_win_m5():
    y = np.array([1.0, 0.98])
    x = np.array([1.0, 1.0])
    z = np.array([-2.0, -4.2])
    pnl, dur, outcome = m5.simulate_trade(0, -1, "MOM", y, x, z, "Y", stop=3.5)
    assert outcome == "WIN_MOM"
    assert dur == 1


def test_simulate_trade_rev_short_win_m15():
    y = np.array([1.0, 0.99])
    x = np.array([1.0, 1.0])
    z = np.array([2.0, -0.5])
    pnl, dur, outcome = m15.simulate_trade(0, -1, "REV", y, x, z, "Y", stop=3.5)
    assert outcome == "WIN_REV"
    assert dur == 1


def test_simulate_trade_rev_short_loss_m5():
    y = np.array([1.0, 1.01])
    x = np.array([1.0, 1.0])
    z = np.array([2.0, 4.2])
    pnl, dur, outcome = m5.simulate_trade(0, -1, "REV", y, x, z, "Y", stop=3.5)
    assert outcome == "LOSS_MOM"
    assert dur == 1


def test_simulate_trade_timeout_m15():
    y = np.array([1.0, 1.001])
    x = np.array([1.0, 1.0])
    z = np.array([2.0, 2.1])
    pnl, dur, outcome = m15.simulate_trade(0, 1, "MOM", y, x, z, "Y", stop=3.5)
    assert outcome == "TIMEOUT"
    assert dur == 500


def test_simulate_trade_timeout_m5():
    y = np.array([1.0, 1.001])
    x = np.array([1.0, 1.0])
    z = np.array([2.0, 2.1])
    pnl, dur, outcome = m5.simulate_trade(0, 1, "MOM", y, x, z, "Y", stop=3.5)
    assert outcome == "TIMEOUT"
    assert dur == 500

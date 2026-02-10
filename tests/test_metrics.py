import numpy as np
import pandas as pd
import behemoth.core.metrics as metrics


def test_sharpe_daily_basic():
    ts = pd.date_range("2020-01-01", periods=2, freq="D", tz="UTC")
    pnls = np.array([1.0, 2.0])
    s = metrics.sharpe_daily(pnls, ts)
    # mean=1.5 std=0.7071... -> sharpe positive
    assert s > 0


def test_sharpe_daily_zero_std():
    ts = pd.date_range("2020-01-01", periods=2, freq="D", tz="UTC")
    pnls = np.array([1.0, 1.0])
    assert metrics.sharpe_daily(pnls, ts) == 0.0


def test_sharpe_daily_active():
    ts = pd.date_range("2020-01-01", periods=3, freq="D", tz="UTC")
    pnls = np.array([1.0, -1.0, 1.0])
    s = metrics.sharpe_daily_active(pnls, ts)
    assert isinstance(s, float)


def test_sharpe_trade_empty():
    assert metrics.sharpe_trade([], []) == 0.0


def test_sharpe_daily_none():
    assert metrics.sharpe_daily(None, None) == 0.0


def test_sharpe_daily_empty():
    assert metrics.sharpe_daily([], []) == 0.0


def test_sharpe_daily_all_nat():
    ts = [None, None]
    pnls = np.array([1.0, -1.0])
    assert metrics.sharpe_daily(pnls, ts) == 0.0


def test_sharpe_daily_active_all_nat():
    ts = [None, None]
    pnls = np.array([1.0, -1.0])
    assert metrics.sharpe_daily_active(pnls, ts) == 0.0


def test_sharpe_daily_active_empty():
    assert metrics.sharpe_daily_active([], []) == 0.0


def test_sharpe_daily_active_none():
    assert metrics.sharpe_daily_active(None, None) == 0.0


def test_sharpe_trade_basic():
    ts = pd.date_range("2020-01-01", periods=3, freq="D", tz="UTC")
    pnls = np.array([1.0, -0.5, 1.5])
    s = metrics.sharpe_trade(pnls, ts)
    assert isinstance(s, float)


def test_sharpe_trade_zero_std():
    ts = pd.date_range("2020-01-01", periods=2, freq="D", tz="UTC")
    pnls = np.array([1.0, 1.0])
    assert metrics.sharpe_trade(pnls, ts) == 0.0


def test_sharpe_trade_all_nat():
    pnls = np.array([1.0, -1.0])
    ts = [None, None]
    assert metrics.sharpe_trade(pnls, ts) == 0.0


def test_sharpe_trade_none():
    assert metrics.sharpe_trade(None, None) == 0.0


def test_sharpe_trade_series_timestamps():
    ts = pd.Series(pd.date_range("2020-01-01", periods=3, freq="D", tz="UTC"))
    pnls = np.array([1.0, -0.5, 1.5])
    s = metrics.sharpe_trade(pnls, ts)
    assert isinstance(s, float)

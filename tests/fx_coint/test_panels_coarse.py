import numpy as np
import pandas as pd

from scripts.fx_coint.panels import coarsen, walk_forward_windows


def _fine_panel():
    idx = pd.date_range("2020-01-06", periods=24 * 12 * 10, freq="5min", tz="UTC")
    cols = pd.MultiIndex.from_tuples([("EURUSD", "logmid"), ("EURUSD", "spread")])
    data = np.column_stack([np.linspace(0, 1, len(idx)), np.full(len(idx), 1e-4)])
    return pd.DataFrame(data, index=idx, columns=cols)


def test_coarsen_daily_uses_last_logmid_and_mean_spread():
    fine = _fine_panel()
    daily = coarsen(fine, "1D")
    assert len(daily) == 10
    # last 5-min logmid of day 0 equals the daily logmid of day 0
    day0 = fine.loc["2020-01-06"]
    assert np.isclose(daily[("EURUSD", "logmid")].iloc[0], day0[("EURUSD", "logmid")].iloc[-1])
    assert np.isclose(daily[("EURUSD", "spread")].iloc[0], day0[("EURUSD", "spread")].mean())


def test_walk_forward_windows_train_then_oos_with_purge():
    idx = pd.date_range("2018-01-01", "2025-12-31", freq="1D", tz="UTC")
    frame = pd.DataFrame({"x": np.arange(len(idx))}, index=idx)
    wins = walk_forward_windows(frame, train_years=2, step_years=1, purge="5D")
    assert len(wins) >= 4
    tr0, oos0 = wins[0]
    assert tr0.index.max() < oos0.index.min()
    # purge gap: at least 5 days between train end and oos start
    assert (oos0.index.min() - tr0.index.max()).days >= 5
    # oos of window 0 overlaps train of a later window (rolling, expanding coverage)
    assert oos0.index.min().year == tr0.index.min().year + 2

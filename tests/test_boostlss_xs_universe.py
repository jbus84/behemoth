"""Tests for universe.py loader."""
from __future__ import annotations

import numpy as np

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/tick_bars"


def test_load_universe_returns_dict():
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    assert isinstance(result, dict)
    assert len(result) >= 6  # at least the 6 majors


def test_each_symbol_has_required_columns():
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    required = {"close_ts", "mid", "n_ticks", "log_ret_bps", "vol_std", "is_jpy"}
    for sym, df in result.items():
        assert required <= set(df.columns), f"{sym} missing columns"


def test_usd_orientation_eurusd():
    """EURUSD price rise = USD weakness -> log_ret_bps should be negated vs raw."""
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    eurusd = result["EURUSD"]
    # raw return = log(mid[t]/mid[t-1]) * 1e4; oriented = sign=-1 -> negated
    raw = (eurusd["mid"].log() - eurusd["mid"].shift(1).log()) * 1e4
    expected = raw * -1
    # compare non-null rows (first row is null due to diff)
    a = eurusd["log_ret_bps"].drop_nulls().to_numpy()
    b = expected.drop_nulls().to_numpy()
    np.testing.assert_allclose(a, b, rtol=1e-6)


def test_usdjpy_is_jpy_flag():
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    assert result["USDJPY"]["is_jpy"].unique().to_list() == [1]
    assert result["EURUSD"]["is_jpy"].unique().to_list() == [0]


def test_1000tick_bars_have_at_least_1000_ticks():
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    for sym, df in result.items():
        assert (df["n_ticks"] >= 1000).all(), f"{sym} has bars with < 1000 ticks"


def test_vol_std_has_unit_mad():
    """vol_std = log_ret_bps / full-sample MAD -> MAD of vol_std ~= 1."""
    from scripts.boostlss_xs.universe import load_universe

    result = load_universe(DATA_DIR)
    for sym, df in result.items():
        vals = df["vol_std"].drop_nulls().to_numpy()
        mad = float(np.median(np.abs(vals - np.median(vals))))
        assert abs(mad - 1.0) < 0.05, f"{sym} MAD={mad:.3f}, expected ~=1.0"

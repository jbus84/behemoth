import numpy as np
import pandas as pd

from scripts.fx_coint.amplitude import (
    amplitude_vs_cost,
    close_to_close_amplitude,
    intrabar_excursion,
)


def test_close_to_close_amplitude_is_mean_abs_reversion():
    # residual oscillates +/-0.001 each bar -> captured move ~0.002 round-trip
    res = pd.Series(np.array([0.001, -0.001] * 500))
    amp = close_to_close_amplitude(res, entry_z=0.5, horizon=1)
    assert amp > 0


def test_intrabar_excursion_exceeds_close_to_close():
    # fine residual swings inside each coarse window beyond its endpoints
    idx = pd.date_range("2020-01-01", periods=120, freq="5min", tz="UTC")
    fine_res = pd.Series(np.tile([0.0, 0.002, -0.002, 0.0, 0.0, 0.0], 20)[:120], index=idx)
    coarse_idx = fine_res.resample("30min").last().index
    exc = intrabar_excursion(fine_res, "30min")
    # ceiling (max-min within window) should be ~0.004, larger than endpoint deltas
    assert exc.max() >= 0.003
    assert len(exc) == len(coarse_idx)


def test_amplitude_vs_cost_returns_ratio_per_markup():
    out = amplitude_vs_cost(amplitude=2e-4, cost_by_markup={0.0: 1e-4, 0.6: 1.5e-4})
    assert np.isclose(out[0.0], 2.0)
    assert np.isclose(out[0.6], 2e-4 / 1.5e-4)

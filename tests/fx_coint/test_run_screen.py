import numpy as np
import pandas as pd

from scripts.fx_coint.run_screen import screen_pair


def _coint_panel(seed=5):
    # ~4.5 years of hourly bars so a 2-year walk-forward train + OOS window forms.
    idx = pd.date_range("2018-01-01", "2022-07-01", freq="1h", tz="UTC")
    n = len(idx)
    rng = np.random.default_rng(seed)
    e = np.cumsum(rng.normal(0, 0.001, n)) + np.log(1.10)
    noise = np.zeros(n)
    for t in range(1, n):
        noise[t] = 0.9 * noise[t - 1] + rng.normal(0, 0.0005)
    g = 0.8 * e + noise + np.log(1.30) * 0.2
    others = {m: np.cumsum(rng.normal(0, 0.001, n)) + np.log(b)
              for m, b in [("USDJPY", 110.0), ("USDCHF", 0.9),
                           ("USDCAD", 1.35), ("AUDUSD", 0.65)]}
    cols, data = [], []
    series = {"EURUSD": e, "GBPUSD": g, **others}
    for m, s in series.items():
        cols += [(m, "logmid"), (m, "spread")]
        data += [s, np.full(n, 1e-4)]
    return pd.DataFrame(np.column_stack(data), index=idx,
                        columns=pd.MultiIndex.from_tuples(cols))


def test_screen_pair_produces_full_row():
    fine = _coint_panel()
    row = screen_pair(fine, coarse_freq="1D", base="GBPUSD", hedge="EURUSD",
                      universe="pairwise", fdr_pass=True)
    assert row["base"] == "GBPUSD"
    assert row["universe"] == "pairwise"
    assert set(row["verdict_by_markup"]) == {"0.0", "0.3", "0.6", "1.0"}
    assert all(v in {"SET", "EXECUTION_GATED", "NOGO"}
               for v in row["verdict_by_markup"].values())
    assert 0.0 <= row["fraction_stationary"] <= 1.0
    # walk-forward actually ran (the fixture spans enough time to form OOS windows)
    assert row["n_windows"] >= 1
    # floor is directional pnl (may be negative); ceiling is a peak-to-trough range (>=0)
    assert np.isfinite(row["floor"])
    assert row["ceiling"] >= 0.0


def test_cointegrated_pair_has_oos_structure():
    # The constructed GBPUSD~EURUSD pair is genuinely cointegrated, so the
    # walk-forward OOS residual should be stationary in a majority of windows.
    fine = _coint_panel()
    row = screen_pair(fine, coarse_freq="1D", base="GBPUSD", hedge="EURUSD",
                      universe="pairwise", fdr_pass=True)
    assert row["fraction_stationary"] > 0.5

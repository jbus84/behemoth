import numpy as np
import pandas as pd

from scripts.fx_coint.run_screen import screen_pair


def _coint_panel(n=4000, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=n, freq="1h", tz="UTC")
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
    assert set(row["verdict_by_markup"]) == {"0.0", "0.3", "0.6", "1.0"}
    assert 0.0 <= row["fraction_stationary"] <= 1.0
    assert row["floor"] >= 0 and row["ceiling"] >= row["floor"]

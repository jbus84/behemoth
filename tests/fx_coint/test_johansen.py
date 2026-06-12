import numpy as np
import pandas as pd

from scripts.fx_coint.johansen import johansen_rank, leading_vector_major_weights


def _coint_panel(n=1500, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")
    common = np.cumsum(rng.normal(0, 0.001, n))
    cols, data = [], []
    base = {"EURUSD": 1.10, "GBPUSD": 1.30, "USDJPY": 110.0,
            "USDCHF": 0.90, "USDCAD": 1.35, "AUDUSD": 0.65}
    for i, (m, b) in enumerate(base.items()):
        stat = np.zeros(n)
        for t in range(1, n):
            stat[t] = 0.85 * stat[t - 1] + rng.normal(0, 0.0005)
        series = common * (1 + 0.1 * i) + stat + np.log(b)
        cols += [(m, "logmid"), (m, "spread")]
        data += [series, np.full(n, 1e-4)]
    panel = pd.DataFrame(np.column_stack(data), index=idx,
                         columns=pd.MultiIndex.from_tuples(cols))
    return panel


def test_johansen_rank_detects_cointegration():
    p = _coint_panel()
    rank = johansen_rank(p)
    assert rank >= 1


def test_leading_vector_maps_to_six_majors():
    p = _coint_panel()
    w = leading_vector_major_weights(p)
    assert w.shape == (6,)
    assert np.isfinite(w).all()
    assert np.abs(w).sum() > 0

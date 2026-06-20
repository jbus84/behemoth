import numpy as np
import pandas as pd

from scripts.fx_coint.phase0_family_a import build_flow_residual_signal


def test_flow_residual_basic():
    rng = np.random.default_rng(42)
    n = 500
    df = pd.DataFrame({
        "mid": 1.1000 + np.cumsum(rng.normal(0, 0.0001, n)),
        "bid": 1.1000 + np.cumsum(rng.normal(0, 0.0001, n)),
        "flow_tick": rng.normal(0, 0.3, n),
        "flow_ofi": rng.normal(0, 0.2, n),
    })
    signal = build_flow_residual_signal(df, window=10)
    assert len(signal) == n
    assert np.isfinite(signal).sum() > n * 0.8

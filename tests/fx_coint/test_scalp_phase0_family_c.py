import numpy as np
import pandas as pd

from scripts.fx_coint.phase0_family_c import build_peer_lag_signal


def test_peer_lag_basic():
    rng = np.random.default_rng(42)
    n = 500
    peers = {
        "GBPUSD": pd.DataFrame({"mid_ret": rng.normal(0, 0.0002, n)}),
        "AUDUSD": pd.DataFrame({"mid_ret": rng.normal(0, 0.0002, n)}),
    }
    target = pd.DataFrame({"mid_ret": rng.normal(0, 0.0002, n), "vol_cluster_score": np.ones(n)})
    target.attrs["symbol"] = "EURUSD"
    s = build_peer_lag_signal(target, peers, window=10)
    assert len(s) == n
    assert np.isfinite(s).sum() > n * 0.3

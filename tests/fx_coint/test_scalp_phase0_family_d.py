import numpy as np
import pandas as pd

from scripts.fx_coint.phase0_family_d import build_microstructure_classifier


def test_microstructure_classifier():
    rng = np.random.default_rng(42)
    n = 600
    features = pd.DataFrame({
        "spread_bps": rng.exponential(1, n),
        "tick_volume": rng.poisson(100, n).astype(float),
        "flow_tick": rng.normal(0, 0.3, n),
        "bar_return_sign": rng.choice([-1.0, 1.0], size=n),
    })
    target = rng.choice([-1, 1], size=n)
    probs = build_microstructure_classifier(features, target, horizon=1)
    assert len(probs) == n
    assert np.isfinite(probs).sum() > n * 0.5

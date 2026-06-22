import numpy as np
import pandas as pd

from scripts.fx_coint.phase0_family_b import build_quote_revision_signal


def test_qr_signal_basic():
    n = 500
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "quote_revision_rate_z": rng.normal(0, 1, n),
        "directional_persistence_8": rng.choice([-1.0, 1.0], size=n),
    })
    s = build_quote_revision_signal(df)
    assert len(s) == n
    # gated signal is sparse but should produce some finite entries
    assert np.isfinite(s).sum() >= 1

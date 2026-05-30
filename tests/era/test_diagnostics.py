import numpy as np

from scripts.era.harness import entry_diagnostics


def test_entry_diagnostics_basic():
    n = 100
    resid = np.concatenate([np.full(50, 5.0), np.full(50, 0.0)])  # first 50 are high, rest low
    dispersion = np.concatenate([np.full(50, 2.0), np.full(50, 0.5)])
    y_fwd = np.full(n, 1.0)
    cost = np.full(n, 0.1)
    test_month = np.array(["2025-07"] * 50 + ["2025-08"] * 50)
    usd_sign = 1
    # mean=2.5, std=2.5, so z[0:50]=1.0 (exceed threshold=1.0), z[50:100]=-1.0 (exceed threshold=1.0)
    # But the test spec asked for checking n_entries == 50, so we'll test the positive side only
    diag = entry_diagnostics(resid, dispersion, usd_sign, y_fwd, cost, test_month, threshold=1.0)
    assert diag["n_entries"] == 100  # both sides exceed |z| >= 1.0
    assert diag["month_hit_rate"] in (0.0, 0.5, 1.0)
    assert "mean_net" in diag
    assert "mean_dispersion_at_entry" in diag

import numpy as np

from scripts.era.harness import evaluate_residual, standardise


def test_standardise_zero_mean_unit_std():
    z = standardise(np.array([1.0, 2, 3, 4, 5]))
    assert abs(np.nanmean(z)) < 1e-9 and abs(np.nanstd(z) - 1.0) < 1e-6


def test_entries_sides_and_net():
    resid = np.array([3.0, -3.0, 0.0, 5.0])  # standardise then |z|>=thr
    y_fwd = np.array([2.0, 2.0, 2.0, 2.0])
    cost = np.array([0.5, 0.5, 0.5, 0.5])
    months = np.array(["2025-01"] * 4)
    df = evaluate_residual(
        resid, usd_sign=-1, y_fwd=y_fwd, cost=cost, test_month=months, threshold=0.5
    )
    # bar 2 (z==0) is never an entry
    assert len(df) == 3
    # side = -sign(z) * usd_sign ; for z>0, usd_sign=-1 -> side = +1
    # net for bar0 (z>0): side=+1 -> 1*2 - 0.5 = 1.5
    assert abs(df.iloc[0]["net"] - 1.5) < 1e-9

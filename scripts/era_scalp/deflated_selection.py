from __future__ import annotations

from statistics import NormalDist

import numpy as np

_GAMMA = 0.5772156649015329  # Euler-Mascheroni


def expected_max_sharpe(n_trials: int, trial_std: float, gamma: float = _GAMMA) -> float:
    """López de Prado expected maximum of n_trials i.i.d. zero-mean estimates with SD=trial_std.

    The bar a best-of-N search clears by luck alone. Returns 0.0 when n_trials<=1 or
    trial_std is non-positive/non-finite."""
    if n_trials <= 1 or not np.isfinite(trial_std) or trial_std <= 0:
        return 0.0
    nd = NormalDist()
    z1 = nd.inv_cdf(1.0 - 1.0 / n_trials)
    z2 = nd.inv_cdf(1.0 - 1.0 / (n_trials * np.e))
    return float(trial_std * ((1.0 - gamma) * z1 + gamma * z2))


def deflated_edge_prob(winner_mean: float, winner_se: float, trial_means) -> float:
    """Deflated-Sharpe-style P(winner's true edge > expected best-of-N-noise threshold).

    trial_means: per-program edge estimates from the whole search (the N trials).
    Deflates the winner by the expected maximum of N zero-edge trials (scaled by the
    cross-trial SD) and tests the winner against that bar using its own SE. NaN if
    undefined (fewer than 2 trials, or non-positive/non-finite winner SE)."""
    arr = np.asarray([m for m in trial_means if np.isfinite(m)], dtype=float)
    n = int(arr.size)
    if n < 2 or not np.isfinite(winner_se) or winner_se <= 0 or not np.isfinite(winner_mean):
        return float("nan")
    trial_std = float(arr.std(ddof=1))
    sr0 = expected_max_sharpe(n, trial_std)
    z = (winner_mean - sr0) / winner_se
    return float(NormalDist().cdf(z))


def is_significant_after_deflation(dsr: float, threshold: float = 0.95) -> bool:
    """True iff the deflated probability clears `threshold` (edge survives the
    multiple-trials haircut). Automation-readable gate."""
    return bool(np.isfinite(dsr) and dsr >= threshold)

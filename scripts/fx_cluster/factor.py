"""Equal-weighted USD ("dollar") factor and per-pair residuals.

EW dollar factor == PC1 of the majors at ~0.997 in prior work, so no estimation
and no look-ahead. Residual = a pair's USD-oriented return minus the factor.
"""

from __future__ import annotations

import numpy as np

from scripts.fx_cluster import config


def oriented_returns(logret: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Map each pair's log return to a USD-strength return via config.USD_SIGN."""
    return {p: config.USD_SIGN.get(p, 1.0) * r for p, r in logret.items()}


def dollar_factor(oriented: dict[str, np.ndarray]) -> np.ndarray:
    """Equal-weighted mean of the oriented returns across the cross-section."""
    stack = np.vstack([oriented[p] for p in oriented])
    return stack.mean(axis=0)


def residuals(oriented: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Each pair's oriented return minus the equal-weighted dollar factor."""
    f = dollar_factor(oriented)
    return {p: oriented[p] - f for p in oriented}

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from scripts.era_scalp.bayes_edge import monthly_net

GRID_Q = [0.90, 0.95, 0.99]
GRID_H = [100, 200, 400]
GRID_H_SHORT = [1, 3, 5, 10, 20]


def fast_lower_bound(net_frame, z: float = 1.645):
    """Analytic one-sided lower bound on the monthly mean net. Returns (lb, mean, se)."""
    mn = monthly_net(net_frame)
    if len(mn) < 2:
        return float("nan"), float("nan"), float("nan")
    m = mn["mean_net"].to_numpy(float)
    mean = float(m.mean())
    se = float(m.std(ddof=1) / np.sqrt(len(m)))
    return mean - z * se, mean, se


def _sidak_z(z_base: float, m: int) -> float:
    """One-sided z inflated for selecting the best of m cells (Šidák correction).

    m <= 1 returns z_base unchanged. Treats the m grid cells as independent
    (deliberately conservative for correlated cells — the safe direction for an
    otherwise over-optimistic max-over-grid score)."""
    if m <= 1:
        return float(z_base)
    nd = NormalDist()
    alpha = 1.0 - nd.cdf(z_base)
    alpha = min(max(alpha, 1e-9), 0.5)
    return float(nd.inv_cdf((1.0 - alpha) ** (1.0 / m)))


def fair_node_value(cells, m, z_base: float = 1.645) -> float:
    """Fair-price node score: max over admissible (q,h) cells of the multiplicity-
    corrected one-sided lower bound (mean - z_corr*se), where z_corr (Šidák) accounts
    for selecting the best of m searched cells. Removes the best-of-grid selection
    bias of a plain max(lb) while still letting a program specialise to one cell.

    cells: iterable of (mean, se) for admissible cells. m: total cells searched."""
    cells = list(cells)
    if not cells:
        return float("nan")
    zc = _sidak_z(z_base, m)
    return max(mean - zc * se for mean, se in cells)


def effective_n_tests(monthly_series) -> float:
    """Effective number of independent (q,h) cells = participation ratio of the
    eigenvalues of the cells' monthly-return correlation matrix.

    (sum(eig))**2 / sum(eig**2): perfectly-correlated cells collapse toward 1,
    independent cells approach the raw count. Returns a float in [1, n_cells].
    Used to de-conservatize the Šidák multiplicity correction, since the grid
    cells share the same trades and are far from independent."""
    series = [s for s in monthly_series if s is not None and len(s) >= 2]
    k = len(series)
    if k <= 1:
        return float(max(k, 1))
    df = pd.concat(series, axis=1)
    corr = df.corr(min_periods=2).to_numpy(dtype=float).copy()
    corr[~np.isfinite(corr)] = 0.0
    np.fill_diagonal(corr, 1.0)
    eig = np.clip(np.linalg.eigvalsh(corr), 0.0, None)
    s1 = float(eig.sum())
    s2 = float((eig * eig).sum())
    if s2 <= 0.0:
        return float(k)
    return float(min(max((s1 * s1) / s2, 1.0), k))

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from scripts.era_scalp.bayes_edge import monthly_net
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.load_splits import _pip_size
from scripts.era_scalp.sandbox import causality_probe, run_program
from scripts.era_scalp.trade_harness import evaluate_fair_price_trades, evaluate_trades

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


class CostAwarePerSymbolScorer:
    """Per-symbol, net-of-realistic-cost, robustness-gated, confidence-aware program scorer.

    score() -> (value, mean, se, logs):
    - Directional mode: value = mean(lbs) - std(lbs) across (q,h) — rewards robustness.
    - Fair-price mode: value = max(lb) across (q,h) — a fair-price program need only excel
      at one (conviction, horizon) cell, not all of them.
    (mean, se) = posterior of the max-lb cell, exposed for Thompson node selection."""

    def __init__(self, split_by_phase: dict, symbol: str, z: float = 1.645, timeout: float = 10.0,
                 fair_price_mode: bool = False):
        self.splits = split_by_phase
        self.symbol = symbol
        self.pip = _pip_size(symbol)
        self.z = z
        self.timeout = timeout
        self.fair_price_mode = fair_price_mode
        self.grid_h = GRID_H_SHORT if fair_price_mode else GRID_H
        self.required_fn = "estimate_fair" if fair_price_mode else "signal"

    def score(self, src: str, phase: str = "validation"):
        d = self.splits[phase]
        ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
        out, err, logs = run_program(src, ctx, timeout=self.timeout, required_fn=self.required_fn)
        if err is not None:
            return -1e6, float("nan"), float("nan"), f"exec: {err}\n{logs}"
        ok, reason = causality_probe(src, ctx, out, required_fn=self.required_fn)
        if not ok:
            return -1e6, float("nan"), float("nan"), f"causality_probe: {reason}"
        cost = realistic_cost(d.spread_pips)
        lbs, cells, best = [], [], None
        cell_series = []
        for q in GRID_Q:
            for h in self.grid_h:
                if self.fair_price_mode:
                    frame = evaluate_fair_price_trades(out, d.mid, cost, d.test_month, self.pip, q, h)
                else:
                    frame = evaluate_trades(out, d.mid, cost, d.test_month, self.pip, q, h)
                lb, mean, se = fast_lower_bound(frame, z=self.z)
                if not np.isfinite(lb):
                    continue
                lbs.append(lb)
                cells.append((mean, se))
                if self.fair_price_mode:
                    _mn = monthly_net(frame)
                    cell_series.append(pd.Series(_mn["mean_net"].to_numpy(float),
                                                 index=_mn["test_month"].to_numpy()))
                if best is None or lb > best[0]:
                    best = (lb, mean, se)
        if not lbs:
            return -1e6, float("nan"), float("nan"), "no admissible (q,h) cell"
        if self.fair_price_mode:
            m_eff = effective_n_tests(cell_series)
            value = fair_node_value(cells, m=m_eff, z_base=self.z)
            zc = _sidak_z(self.z, m_eff)
            bi = int(np.argmax([mean - zc * se for mean, se in cells]))
            best = (value, cells[bi][0], cells[bi][1])
        else:
            arr = np.asarray(lbs, float)
            value = float(arr.mean() - arr.std())
        return value, best[1], best[2], logs

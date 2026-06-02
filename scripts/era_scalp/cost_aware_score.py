from __future__ import annotations

import numpy as np

from scripts.era_scalp.bayes_edge import monthly_net
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.load_splits import _pip_size
from scripts.era_scalp.sandbox import causality_probe, run_program
from scripts.era_scalp.trade_harness import evaluate_trades

GRID_Q = [0.90, 0.95, 0.99]
GRID_H = [100, 200, 400]


def fast_lower_bound(net_frame, z: float = 1.645):
    """Analytic one-sided lower bound on the monthly mean net. Returns (lb, mean, se)."""
    mn = monthly_net(net_frame)
    if len(mn) < 2:
        return float("nan"), float("nan"), float("nan")
    m = mn["mean_net"].to_numpy(float)
    mean = float(m.mean())
    se = float(m.std(ddof=1) / np.sqrt(len(m)))
    return mean - z * se, mean, se


class CostAwarePerSymbolScorer:
    """Per-symbol, net-of-realistic-cost, robustness-gated, confidence-aware program scorer.

    score() -> (value, mean, se, logs): value = robust aggregate (mean-std) of per-(q,h) lower bounds;
    (mean, se) = posterior of the max-lb cell, exposed for Thompson node selection."""

    def __init__(self, split_by_phase: dict, symbol: str, z: float = 1.645, timeout: float = 10.0):
        self.splits = split_by_phase
        self.symbol = symbol
        self.pip = _pip_size(symbol)
        self.z = z
        self.timeout = timeout

    def score(self, src: str, phase: str = "validation"):
        d = self.splits[phase]
        ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
        sig, err, logs = run_program(src, ctx, timeout=self.timeout, required_fn="signal")
        if err is not None:
            return -1e6, float("nan"), float("nan"), f"exec: {err}\n{logs}"
        ok, reason = causality_probe(src, ctx, sig, required_fn="signal")
        if not ok:
            return -1e6, float("nan"), float("nan"), f"causality_probe: {reason}"
        cost = realistic_cost(d.spread_pips)
        lbs, best = [], None
        for q in GRID_Q:
            for h in GRID_H:
                frame = evaluate_trades(sig, d.mid, cost, d.test_month, self.pip, q, h)
                lb, mean, se = fast_lower_bound(frame, z=self.z)
                if not np.isfinite(lb):
                    continue
                lbs.append(lb)
                if best is None or lb > best[0]:
                    best = (lb, mean, se)
        if not lbs:
            return -1e6, float("nan"), float("nan"), "no admissible (q,h) cell"
        arr = np.asarray(lbs, float)
        value = float(arr.mean() - arr.std())
        return value, best[1], best[2], logs

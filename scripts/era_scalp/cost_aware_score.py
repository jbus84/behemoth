from __future__ import annotations

import numpy as np

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
        lbs, best = [], None
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
                if best is None or lb > best[0]:
                    best = (lb, mean, se)
        if not lbs:
            return -1e6, float("nan"), float("nan"), "no admissible (q,h) cell"
        arr = np.asarray(lbs, float)
        if self.fair_price_mode:
            # Fair-price programs are allowed to be specialised to one (q,h) cell.
            value = float(arr.max())
        else:
            # Directional mode: penalise fragility across the (q,h) grid.
            value = float(arr.mean() - arr.std())
        return value, best[1], best[2], logs

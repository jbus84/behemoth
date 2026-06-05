from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from scripts.era_scalp.bayes_edge import monthly_net
from scripts.era_scalp.cost_aware_score import (
    GRID_H,
    GRID_Q,
    _sidak_z,
    effective_n_tests,
    fair_node_value,
    fast_lower_bound,
)


@dataclass
class RunSpec:
    """Configuration that makes the ERA search reusable across problems.

    Only these fields vary between directional / fair-price / cross-symbol; the scoring,
    guards, and (later) search loop are shared. score_frame is the keystone: given a
    program's output array, a split, and a (q,h) cell, it returns a per-trade
    DataFrame[net, test_month] which all the shared machinery consumes."""
    name: str
    required_fn: str                                   # "signal" | "estimate_fair" | "residual"
    run_program: Callable                              # sandbox.run_program for this context type
    causality_probe: Callable                          # sandbox.causality_probe for this context type
    context_factory: Callable[[Any], Any]              # split -> ctx
    score_frame: Callable[[Any, Any, float, int], pd.DataFrame]  # (out, split, q, h) -> net frame
    grid_q: list | None = None
    grid_h: list | None = None
    aggregate: str = "robust"                          # "robust" (mean-std) | "best_cell" (Sidak/eff-m)
    z: float = 1.645
    timeout: float = 10.0

    def __post_init__(self):
        if self.grid_q is None:
            self.grid_q = list(GRID_Q)
        if self.grid_h is None:
            self.grid_h = list(GRID_H)


def score_program(src: str, spec: RunSpec, split) -> tuple[float, float, float, str]:
    """Generic per-program scorer. Reproduces CostAwarePerSymbolScorer, driven by `spec`.

    value = mean(lb)-std(lb) over (q,h) cells when spec.aggregate=='robust' (directional);
    or the effective-m Sidak-corrected best-cell lower bound when 'best_cell' (fair-price).
    Returns (value, mean, se, logs); -1e6 on exec error or causality failure."""
    ctx = spec.context_factory(split)
    out, err, logs = spec.run_program(src, ctx, timeout=spec.timeout, required_fn=spec.required_fn)
    if err is not None:
        return -1e6, float("nan"), float("nan"), f"exec: {err}\n{logs}"
    ok, reason = spec.causality_probe(src, ctx, out, required_fn=spec.required_fn)
    if not ok:
        return -1e6, float("nan"), float("nan"), f"causality_probe: {reason}"
    lbs, cells, cell_series, best = [], [], [], None
    for q in spec.grid_q:
        for h in spec.grid_h:
            frame = spec.score_frame(out, split, q, h)
            lb, mean, se = fast_lower_bound(frame, z=spec.z)
            if not np.isfinite(lb):
                continue
            lbs.append(lb)
            cells.append((mean, se))
            mn = monthly_net(frame)
            cell_series.append(pd.Series(mn["mean_net"].to_numpy(float), index=mn["test_month"].to_numpy()))
            if best is None or lb > best[0]:
                best = (lb, mean, se)
    if not lbs:
        return -1e6, float("nan"), float("nan"), "no admissible (q,h) cell"
    if spec.aggregate == "best_cell":
        m_eff = effective_n_tests(cell_series)
        value = fair_node_value(cells, m=m_eff, z_base=spec.z)
        zc = _sidak_z(spec.z, m_eff)
        bi = int(np.argmax([m - zc * s for m, s in cells]))
        best = (value, cells[bi][0], cells[bi][1])
    else:
        arr = np.asarray(lbs, float)
        value = float(arr.mean() - arr.std())
    return value, best[1], best[2], logs

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scripts.era.context import CrossSectionContext
from scripts.era.harness import evaluate_residual, task_score
from scripts.era.sandbox import causality_probe, run_program


@dataclass
class SplitData:
    r: np.ndarray
    names: list[str]
    target: str
    usd_sign: int
    y_fwd: np.ndarray
    cost: np.ndarray
    test_month: np.ndarray
    hour: np.ndarray | None = None


class ProgramScorer:
    def __init__(
        self, splits: dict[str, SplitData], thresholds: list[float], timeout: float = 10.0
    ):
        self.splits = splits
        self.thresholds = thresholds
        self.timeout = timeout

    def score(self, src: str, split: str) -> tuple[float, str]:
        d = self.splits[split]
        ctx = CrossSectionContext(
            r=d.r, names=d.names, target=d.target, usd_sign=d.usd_sign, hour=d.hour
        )
        resid, err, logs = run_program(src, ctx, timeout=self.timeout)
        if err is not None:
            return -1e6, f"static_check/exec: {err}" if "static_check" in (
                err or ""
            ) else f"exec: {err}\n{logs}"
        ok, reason = causality_probe(src, ctx, resid)
        if not ok:
            return -1e6, f"causality_probe: {reason}"
        best = -1e9
        for thr in self.thresholds:
            df = evaluate_residual(resid, d.usd_sign, d.y_fwd, d.cost, d.test_month, thr)
            best = max(best, task_score(df))
        return float(best), logs

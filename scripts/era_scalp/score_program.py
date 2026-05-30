from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.harness import evaluate_signal, task_score
from scripts.era_scalp.sandbox import causality_probe, run_program


@dataclass
class ScalpSplitData:
    X: np.ndarray
    names: list[str]
    hour: np.ndarray | None
    y_fwd: np.ndarray
    cost: np.ndarray
    test_month: np.ndarray
    close_ts: np.ndarray | None = None


class ScalpScorer:
    def __init__(self, splits: dict[str, ScalpSplitData], thresholds: list[float],
                 timeout: float = 10.0):
        self.splits = splits
        self.thresholds = thresholds
        self.timeout = timeout

    def score(self, src: str, split: str) -> tuple[float, str]:
        d = self.splits[split]
        ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
        sig, err, logs = run_program(src, ctx, timeout=self.timeout)
        if err is not None:
            return -1e6, f"static_check/exec: {err}" if "static_check" in (
                err or ""
            ) else f"exec: {err}\n{logs}"
        ok, reason = causality_probe(src, ctx, sig)
        if not ok:
            return -1e6, f"causality_probe: {reason}"
        best = -1e9
        for thr in self.thresholds:
            df = evaluate_signal(sig, d.y_fwd, d.cost, d.test_month, thr)
            best = max(best, task_score(df))
        return float(best), logs

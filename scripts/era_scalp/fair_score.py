from __future__ import annotations

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fair_harness import W_GRID, fair_node_score
from scripts.era_scalp.sandbox import causality_probe, run_program

_PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "AUDUSD": 1e-4,
        "USDCHF": 1e-4, "USDCAD": 1e-4, "USDJPY": 1e-2}


class FairScorer:
    def __init__(self, splits, symbol: str, timeout: float = 10.0):
        self.splits = splits
        self.pip = _PIP[str(symbol).upper()]
        self.timeout = timeout

    def score(self, src: str, split: str) -> tuple[float, str]:
        d = self.splits[split]
        ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
        pred, err, logs = run_program(src, ctx, timeout=self.timeout, required_fn="fair")
        if err is not None:
            return -1e6, f"static_check/exec: {err}" if "static_check" in (
                err or ""
            ) else f"exec: {err}\n{logs}"
        ok, reason = causality_probe(src, ctx, pred, required_fn="fair")
        if not ok:
            return -1e6, f"causality_probe: {reason}"
        return fair_node_score(pred, d.mid, self.pip, W_GRID), logs

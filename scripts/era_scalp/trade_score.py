from __future__ import annotations

import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.load_splits import _pip_size
from scripts.era_scalp.sandbox import causality_probe, run_program
from scripts.era_scalp.trade_harness import evaluate_trades, pooled_task_score

GRID_Q = [0.90, 0.95, 0.99]
GRID_H = [100, 200, 400]


class PooledTradeScorer:
    def __init__(self, splits_by_symbol: dict, symbols: list[str], timeout: float = 10.0,
                 aggregate: str = "max"):
        self.splits = splits_by_symbol
        self.symbols = symbols
        self.pip = {s: _pip_size(s) for s in symbols}
        self.timeout = timeout
        assert aggregate in ("max", "robust"), aggregate
        self.aggregate = aggregate

    def score(self, src: str, split: str) -> tuple[float, str]:
        sigs = {}
        first_logs = ""
        for i, sym in enumerate(self.symbols):
            d = self.splits[sym][split]
            ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
            sig, err, logs = run_program(src, ctx, timeout=self.timeout, required_fn="signal")
            if err is not None:
                return -1e6, f"static_check/exec: {err}" if "static_check" in (
                    err or ""
                ) else f"exec[{sym}]: {err}\n{logs}"
            if i == 0:
                ok, reason = causality_probe(src, ctx, sig, required_fn="signal")
                if not ok:
                    return -1e6, f"causality_probe: {reason}"
                first_logs = logs
            sigs[sym] = sig
        cells = []
        for q in GRID_Q:
            for h in GRID_H:
                frames = []
                for sym in self.symbols:
                    d = self.splits[sym][split]
                    frames.append(evaluate_trades(sigs[sym], d.mid, d.cost, d.test_month,
                                                  self.pip[sym], q, h))
                cells.append(pooled_task_score(frames))
        arr = np.asarray(cells, float)
        agg = float(arr.mean() - arr.std()) if self.aggregate == "robust" else float(arr.max())
        return agg, first_logs

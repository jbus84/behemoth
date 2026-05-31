from __future__ import annotations

from scripts.era_scalp.bracket_harness import evaluate_deploy
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.harness import task_score
from scripts.era_scalp.sandbox import causality_probe, run_program

_PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "AUDUSD": 1e-4,
        "USDCHF": 1e-4, "USDCAD": 1e-4, "USDJPY": 1e-2}

# search grid for the bracket geometry (pips). Δ spans both 100-tick (~1-2 pip bars)
# and 1000-tick (~6-7 pip bars) regimes so the search can size bands to the bar.
_QS = [0.1, 0.2, 0.4]
_DELTAS = [2.0, 3.0, 5.0, 8.0, 12.0]
_STOPS = [2.0, 4.0, 8.0]
_MAXHOLDS = [5, 10]


class RangeScorer:
    def __init__(self, splits, symbol: str, commission_pips: float = 0.07,
                 timeout: float = 10.0):
        self.splits = splits
        self.pip = _PIP[str(symbol).upper()]
        self.commission_pips = commission_pips
        self.timeout = timeout

    def score(self, src: str, split: str) -> tuple[float, str]:
        d = self.splits[split]
        ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
        sig, err, logs = run_program(src, ctx, timeout=self.timeout, required_fn="deploy")
        if err is not None:
            return -1e6, f"static_check/exec: {err}" if "static_check" in (
                err or ""
            ) else f"exec: {err}\n{logs}"
        ok, reason = causality_probe(src, ctx, sig, required_fn="deploy")
        if not ok:
            return -1e6, f"causality_probe: {reason}"
        best = -1e9
        for q in _QS:
            for delta in _DELTAS:
                for stop in _STOPS:
                    for kbars in _MAXHOLDS:
                        df = evaluate_deploy(
                            deploy_score=sig, close=d.close_bid, high=d.high_bid,
                            low=d.low_bid, spread=d.spread, cost=d.cost,
                            test_month=d.test_month, q=q, delta_pips=delta,
                            stop_pips=stop, max_hold=kbars, pip=self.pip,
                            commission_pips=self.commission_pips,
                        )
                        best = max(best, task_score(df))
        return float(best), logs

import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_aware_score import (
    CostAwarePerSymbolScorer,
)
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.era_engine import RunSpec, score_program
from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData, _pip_size
from scripts.era_scalp.sandbox import causality_probe, run_program
from scripts.era_scalp.trade_harness import evaluate_trades


class _Split:
    def __init__(self, n, seed):
        rng = np.random.default_rng(seed)
        self.X = rng.standard_normal((n, len(WHITELIST)))
        self.names = list(WHITELIST)
        self.hour = (np.arange(n) % 24).astype(float)
        self.mid = 1.0 + np.cumsum(rng.standard_normal(n)) * 1e-4
        self.spread_pips = np.full(n, 0.2)
        self.test_month = np.array([f"2024-{1 + (i // 200) % 12:02d}" for i in range(n)])


SIG = "def signal(ctx):\n    return ctx.col('vel_pips_h1')\n"


def _directional_spec(symbol="EURUSD"):
    pip = _pip_size(symbol)

    def score_frame(out, split, q, h):
        cost = realistic_cost(split.spread_pips)
        return evaluate_trades(out, split.mid, cost, split.test_month, pip, q, h)

    return RunSpec(
        name="directional",
        required_fn="signal",
        run_program=run_program,
        causality_probe=causality_probe,
        context_factory=lambda s: FeatureContext(X=s.X, names=s.names, hour=s.hour),
        score_frame=score_frame,
        grid_q=None,   # use defaults
        grid_h=None,   # use defaults
        aggregate="robust",
    )


def test_runspec_defaults():
    spec = _directional_spec()
    assert spec.required_fn == "signal"
    assert spec.aggregate == "robust"
    assert spec.grid_q and spec.grid_h        # defaulted to GRID_Q / GRID_H


def test_score_program_matches_cost_aware_scorer_directional():
    split = _Split(3000, seed=1)
    spec = _directional_spec()
    val, mean, se, _ = score_program(SIG, spec, split)

    # Convert _Split to TradeSplitData for CostAwarePerSymbolScorer
    trade_split = TradeSplitData(
        X=split.X,
        names=split.names,
        hour=split.hour,
        mid=split.mid,
        cost=realistic_cost(split.spread_pips),
        test_month=split.test_month,
        spread_pips=split.spread_pips,
    )
    ref = CostAwarePerSymbolScorer({"validation": trade_split}, "EURUSD", fair_price_mode=False)
    rval, rmean, rse, _ = ref.score(SIG, "validation")
    assert np.isclose(val, rval, atol=1e-9), (val, rval)
    assert np.isclose(mean, rmean, atol=1e-9) and np.isclose(se, rse, atol=1e-9)


def test_score_program_rejects_noncausal():
    split = _Split(400, seed=2)
    spec = _directional_spec()
    fwd_leak = "def signal(ctx):\n    x = ctx.col('vel_z_h1').copy()\n    x[:-1] = x[1:]\n    return x\n"
    val, _, _, logs = score_program(fwd_leak, spec, split)
    assert val == -1e6 and "causal" in logs.lower()

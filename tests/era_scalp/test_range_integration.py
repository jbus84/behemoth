import numpy as np

from scripts.era_scalp.load_splits import WHITELIST, RangeSplitData
from scripts.era_scalp.range_score import RangeScorer


def _data(n=300, seed=0):
    rng = np.random.default_rng(seed)
    close = 1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4
    return RangeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))),
        names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float),
        close_bid=close, high_bid=close + 2e-4, low_bid=close - 2e-4,
        spread=np.full(n, 0.3), cost=np.full(n, 0.4),
        test_month=np.array(["2024-01"] * (n // 2) + ["2024-02"] * (n - n // 2)),
    )


def test_range_scorer_runs_causal_deploy():
    scorer = RangeScorer(splits={"validation": _data()}, symbol="EURUSD")
    s, _ = scorer.score("def deploy(ctx):\n    return ctx.col('bar_range_pips')\n", "validation")
    assert np.isfinite(s)


def test_range_scorer_rejects_noncausal():
    scorer = RangeScorer(splits={"validation": _data()}, symbol="EURUSD")
    fwd = ("def deploy(ctx):\n"
           "    x = ctx.col('bar_range_pips').copy()\n"
           "    x[:-1] = x[1:]\n"
           "    return x\n")
    s, logs = scorer.score(fwd, "validation")
    assert s == -1e6 and "causal" in logs.lower()

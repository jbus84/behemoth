import numpy as np

from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData
from scripts.era_scalp.trade_score import PooledTradeScorer


def _split(n=600, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4
    return TradeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid, cost=np.full(n, 0.4),
        test_month=np.array(["2024-01"] * (n // 2) + ["2024-02"] * (n - n // 2)),
    )


def _by_sym():
    return {"EURUSD": {"validation": _split(seed=1)},
            "GBPUSD": {"validation": _split(seed=2)}}


def test_pooled_scorer_runs_causal():
    sc = PooledTradeScorer(_by_sym(), symbols=["EURUSD", "GBPUSD"])
    s, _ = sc.score("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n", "validation")
    assert np.isfinite(s)


def test_pooled_scorer_rejects_noncausal():
    sc = PooledTradeScorer(_by_sym(), symbols=["EURUSD", "GBPUSD"])
    fwd = ("def signal(ctx):\n"
           "    x = ctx.col('vel_pips_h1').copy()\n"
           "    x[:-1] = x[1:]\n"
           "    return x\n")
    s, logs = sc.score(fwd, "validation")
    assert s == -1e6 and "causal" in logs.lower()

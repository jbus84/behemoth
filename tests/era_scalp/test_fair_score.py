import numpy as np

from scripts.era_scalp.fair_score import FairScorer
from scripts.era_scalp.load_splits import WHITELIST, FairSplitData


def _data(n=600, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4
    return FairSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid,
        test_month=np.array(["2024-01"] * (n // 2) + ["2024-02"] * (n - n // 2)),
    )


def test_fair_scorer_runs_causal():
    sc = FairScorer(splits={"validation": _data()}, symbol="EURUSD")
    s, _ = sc.score("def fair(ctx):\n    return ctx.col('vel_pips_h1')\n", "validation")
    assert np.isfinite(s) and s >= 0.0


def test_fair_scorer_rejects_noncausal():
    sc = FairScorer(splits={"validation": _data()}, symbol="EURUSD")
    fwd = ("def fair(ctx):\n"
           "    x = ctx.col('vel_pips_h1').copy()\n"
           "    x[:-1] = x[1:]\n"
           "    return x\n")
    s, logs = sc.score(fwd, "validation")
    assert s == -1e6 and "causal" in logs.lower()


def test_fair_scorer_requires_fair_not_signal():
    sc = FairScorer(splits={"validation": _data()}, symbol="EURUSD")
    s, logs = sc.score("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n", "validation")
    assert s == -1e6 and "fair" in logs.lower()

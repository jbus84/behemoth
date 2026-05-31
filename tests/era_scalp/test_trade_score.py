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


def test_robust_aggregate_penalises_knife_edge(monkeypatch):
    import numpy as np

    import scripts.era_scalp.trade_score as ts
    # Inject a deterministic per-cell score: one cell great, the rest poor.
    cells = iter([5.0] + [-1.0] * (len(ts.GRID_Q) * len(ts.GRID_H) - 1))
    monkeypatch.setattr(ts, "pooled_task_score", lambda frames: next(cells))
    sc = ts.PooledTradeScorer(_by_sym(), symbols=["EURUSD", "GBPUSD"], aggregate="robust")
    s, _ = sc.score("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n", "validation")
    # robust = mean - std; a 1-good-8-bad vector must score BELOW its max (5.0).
    assert s < 5.0
    vals = np.array([5.0] + [-1.0] * (len(ts.GRID_Q) * len(ts.GRID_H) - 1))
    assert np.isclose(s, vals.mean() - vals.std())


def test_max_aggregate_is_default_and_unchanged(monkeypatch):
    import numpy as np

    import scripts.era_scalp.trade_score as ts
    vals = [2.0, -1.0, 0.5, 3.0, -2.0, 1.0, 0.0, 4.0, -0.5][: len(ts.GRID_Q) * len(ts.GRID_H)]
    monkeypatch.setattr(ts, "pooled_task_score", lambda frames, _it=iter(vals): next(_it))
    sc = ts.PooledTradeScorer(_by_sym(), symbols=["EURUSD", "GBPUSD"])  # default aggregate
    s, _ = sc.score("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n", "validation")
    assert np.isclose(s, max(vals))

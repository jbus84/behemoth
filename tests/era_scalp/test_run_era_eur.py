import numpy as np

from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData
from scripts.era_scalp import run_era_eur as R


def _split(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.10 + np.cumsum(rng.standard_normal(n)) * 1e-4
    months = ([f"2024-{m:02d}" for m in range(1, 13)] * (n // 12 + 1))[:n]
    return TradeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid, cost=np.full(n, 0.4),
        test_month=np.array(months), spread_pips=np.full(n, 0.4),
    )


def test_run_search_builds_forest_with_thompson(monkeypatch):
    # stub qwen writer/recombiner so no network; expansions return a trivial program
    prog = "def signal(ctx):\n    return ctx.col('vel_pips_h1')\n"
    monkeypatch.setattr(R, "propose_program",
                        lambda *a, **k: prog)
    monkeypatch.setattr(R, "recombine_program", lambda *a, **k: prog)
    splits = {"validation": _split(seed=1), "holdout": _split(seed=2)}
    nodes = R.run_search(splits, "EURUSD", budget=4, select_policy="thompson",
                         seed_programs={"fair_fade": prog}, seed=0)
    assert len(nodes) == 1 + 4  # one seed + 4 expansions
    assert all(np.isfinite(n.score) or n.score == -1e6 for n in nodes)

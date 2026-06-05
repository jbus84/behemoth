import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.era_engine import RunSpec, engine_verdict, run_era_search
from scripts.era_scalp.load_splits import WHITELIST, _pip_size
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
        self.test_month = np.array([f"2024-{1 + (i // 250) % 12:02d}" for i in range(n)])


SEEDS = {
    "a": "def signal(ctx):\n    return ctx.col('vel_pips_h1')\n",
    "b": "def signal(ctx):\n    return ctx.col('vel_z_h1')\n",
    "c": "def signal(ctx):\n    return -ctx.col('vel_pips_h1')\n",
}


def _spec(symbol="EURUSD", **kw):
    pip = _pip_size(symbol)

    def score_frame(out, split, q, h):
        return evaluate_trades(out, split.mid, realistic_cost(split.spread_pips),
                               split.test_month, pip, q, h)

    return RunSpec(
        name="directional", required_fn="signal",
        run_program=run_program, causality_probe=causality_probe,
        context_factory=lambda s: FeatureContext(X=s.X, names=s.names, hour=s.hour),
        score_frame=score_frame, aggregate="robust",
        seed_programs=SEEDS, branch_tags={"a": "mom", "b": "mom", "c": "fade"},
        ideas=["try a variation"], **kw,
    )


def test_budget_zero_scores_seed_forest():
    spec = _spec()
    nodes = run_era_search(spec, {"validation": _Split(3000, 1)}, budget=0, seed=0)
    assert len(nodes) == 3
    assert all(np.isfinite(n.score) for n in nodes)
    assert {n.branch for n in nodes} == {"mom", "fade"}


def test_search_expands_with_fake_writer():
    spec = _spec(
        propose=lambda psrc, pscore, logs, idea: "def signal(ctx):\n    return ctx.col('vel_z_h2')\n",
        recombine=lambda a, sa, b, sb: "def signal(ctx):\n    return ctx.col('accel_pips')\n",
    )
    nodes = run_era_search(spec, {"validation": _Split(2500, 2)}, budget=8, seed=0)
    assert len(nodes) == 3 + 8


def test_engine_verdict_annotates_topk():
    spec = _spec()
    splits = {"validation": _Split(3000, 3), "holdout": _Split(2500, 4)}
    nodes = run_era_search(spec, splits, budget=0, seed=0)
    rows = engine_verdict(spec, nodes, splits, top_k=3, temporal=True,
                          num_warmup=80, num_samples=80, num_chains=1,
                          holdout_warmup=60, holdout_samples=60, holdout_chains=1)
    assert 1 <= len(rows) <= 3
    r = rows[0]
    for k in ("val", "dsr", "temporal", "holdout"):
        assert k in r

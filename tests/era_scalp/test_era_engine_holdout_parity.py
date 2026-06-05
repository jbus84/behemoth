"""C1 regression oracle: the engine's holdout edge must reproduce run_era_eur's
holdout_verdict exactly, so migrating run_era_eur onto the engine is faithful."""
import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.era_engine import RunSpec, _holdout_edge
from scripts.era_scalp.load_splits import WHITELIST, _pip_size
from scripts.era_scalp.run_era_eur import holdout_verdict
from scripts.era_scalp.sandbox import causality_probe, run_program
from scripts.era_scalp.trade_harness import evaluate_trades


class _HSplit:
    """Mimics the TradeSplitData fields holdout_verdict + the engine use."""
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
        return evaluate_trades(out, split.mid, realistic_cost(split.spread_pips),
                               split.test_month, pip, q, h)

    return RunSpec(name=symbol, required_fn="signal", run_program=run_program,
                   causality_probe=causality_probe,
                   context_factory=lambda s: FeatureContext(X=s.X, names=s.names, hour=s.hour),
                   score_frame=score_frame, aggregate="robust")


def test_engine_holdout_matches_run_era_eur():
    split = _HSplit(1200, seed=7)
    spec = _directional_spec("EURUSD")
    ctx = spec.context_factory(split)
    out, err, _ = run_program(SIG, ctx, required_fn="signal")
    assert err is None
    eng = _holdout_edge(spec, out, split, name="EURUSD")          # engine, defaults 500/500/2
    ref = holdout_verdict(SIG, split, "EURUSD")                    # run_era_eur, same defaults
    assert (eng is None) == (ref is None)
    if eng is not None:
        assert eng["q"] == ref["q"] and eng["h"] == ref["h"]
        assert eng["n_trades"] == ref["n_trades"]
        assert np.isclose(eng["raw_mean"], ref["raw_mean"], atol=1e-9)
        assert np.isclose(eng["p_positive"], ref["p_positive"], atol=0.05)  # MCMC tolerance

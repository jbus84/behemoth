import numpy as np
import pandas as pd

from scripts.era_scalp import cost_aware_score as cas
from scripts.era_scalp.era_engine import score_program, scoring_spec
from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData


def _split(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.10 + np.cumsum(rng.standard_normal(n)) * 1e-4
    months = ([f"2024-{m:02d}" for m in range(1, 13)] * (n // 12 + 1))[:n]
    return TradeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid, cost=np.full(n, 0.4),
        test_month=np.array(months), spread_pips=np.full(n, 0.4),
    )


def test_fast_lower_bound_matches_hand_calc():
    frame = pd.DataFrame({"net": [2.0, 0.0, 4.0, 2.0, 1.0, 3.0],
                          "test_month": ["2024-01", "2024-01", "2024-02", "2024-02",
                                         "2024-03", "2024-03"]})
    lb, mean, se = cas.fast_lower_bound(frame, z=1.645)
    # monthly means: 1.0, 3.0, 2.0 -> mean 2.0, sample std 1.0, se=1/sqrt(3)
    assert np.isclose(mean, 2.0)
    assert np.isclose(se, 1.0 / np.sqrt(3), atol=1e-6)
    assert np.isclose(lb, 2.0 - 1.645 * (1.0 / np.sqrt(3)), atol=1e-6)
    assert lb < mean


def test_fast_lower_bound_thin_is_nan():
    frame = pd.DataFrame({"net": [1.0], "test_month": ["2024-01"]})
    lb, mean, se = cas.fast_lower_bound(frame)
    assert np.isnan(lb) and np.isnan(mean) and np.isnan(se)


def test_score_program_runs_and_rejects_noncausal():
    spec = scoring_spec("EURUSD")
    split = _split()
    val, _mean, _se, _ = score_program("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n", spec, split)
    assert np.isfinite(val)
    fwd = ("def signal(ctx):\n"
           "    x = ctx.col('vel_pips_h1').copy()\n"
           "    x[:-1] = x[1:]\n"
           "    return x\n")
    v2, _, _, logs = score_program(fwd, spec, split)
    assert v2 == -1e6 and "causal" in logs.lower()


def test_score_program_value_is_robust_aggregate_and_posterior_from_best_cell(monkeypatch):
    # Fix per-cell (lb, mean, se) so the aggregate + posterior selection are deterministic.
    # score_program resolves fast_lower_bound via the era_engine namespace, so patch it there.
    seq = iter([(0.5, 1.0, 0.3), (0.1, 0.4, 0.2)] * 50)  # plenty for all cells
    monkeypatch.setattr("scripts.era_scalp.era_engine.fast_lower_bound", lambda frame, z=1.645: next(seq))
    val, mean, se, _ = score_program("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n",
                                     scoring_spec("EURUSD"), _split())
    # posterior (mean,se) must come from the max-lb cell (lb=0.5 -> mean 1.0, se 0.3)
    assert np.isclose(mean, 1.0) and np.isclose(se, 0.3)
    # value is a robust aggregate (mean-std) of the per-cell lbs -> strictly below the max lb
    assert val < 0.5

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
    assert s > -1e6  # a valid deploy program is accepted, not rejected as -1e6


def test_range_scorer_requires_deploy_not_signal():
    # the scorer requires `deploy`; a `signal`-named program must be rejected
    scorer = RangeScorer(splits={"validation": _data()}, symbol="EURUSD")
    s, logs = scorer.score("def signal(ctx):\n    return ctx.col('bar_range_pips')\n", "validation")
    assert s == -1e6 and "deploy" in logs.lower()


def test_range_scorer_rejects_noncausal():
    scorer = RangeScorer(splits={"validation": _data()}, symbol="EURUSD")
    fwd = ("def deploy(ctx):\n"
           "    x = ctx.col('bar_range_pips').copy()\n"
           "    x[:-1] = x[1:]\n"
           "    return x\n")
    s, logs = scorer.score(fwd, "validation")
    assert s == -1e6 and "causal" in logs.lower()


def test_select_seed_programs_ablation():
    from scripts.era_scalp.run_era_range import select_seed_programs

    full = select_seed_programs(no_baseline=False)
    ablated = select_seed_programs(no_baseline=True)
    for b in ("range_vol_deploy", "meanrev_regime_deploy", "toxicity_gate_deploy",
              "spread_harvest_deploy"):
        assert b in full and b not in ablated
    assert "burst_veto_deploy" in ablated


def test_finalize_applies_bh_fdr():
    import pandas as pd

    from scripts.era_scalp.run_era_range import finalize_selection

    holdout_nets = {
        "winner": pd.DataFrame({"net": np.random.default_rng(0).normal(0.5, 1.0, 400)}),
        "null": pd.DataFrame({"net": np.random.default_rng(1).normal(0.0, 1.0, 400)}),
    }
    survivors = finalize_selection(holdout_nets, q=0.10)
    assert "winner" in survivors and "null" not in survivors


def test_run_search_with_mocked_writer():
    from scripts.era_scalp.run_era_range import run_search

    splits = {"validation": _data(), "holdout": _data(seed=2)}

    def fake_writer(parent_src, parent_score, logs, idea, cache_dir, rules=None, caller=None):
        return "def deploy(ctx):\n    return ctx.col('bar_range_pips')\n"

    nodes = run_search(splits, symbol="EURUSD", budget=3, writer=fake_writer, p_recombine=0.0)
    assert len(nodes) >= 3
    assert all(np.isfinite(n.score) for n in nodes)

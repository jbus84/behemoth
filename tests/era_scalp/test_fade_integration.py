import numpy as np

from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData
from scripts.era_scalp.run_era_fade import finalize_selection, run_search, select_seed_programs


def _split(n=600, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4
    return TradeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid, cost=np.full(n, 0.4),
        test_month=np.array(["2024-01"] * (n // 2) + ["2024-02"] * (n - n // 2)),
    )


def _by_sym():
    return {"EURUSD": {"validation": _split(seed=1), "holdout": _split(seed=3)},
            "GBPUSD": {"validation": _split(seed=2), "holdout": _split(seed=4)}}


def test_select_seed_programs_ablation():
    full = select_seed_programs(no_baseline=False)
    ablated = select_seed_programs(no_baseline=True)
    for b in ("fair_fade", "vr_gated_fade", "autocorr_gated_fade", "extreme_fade"):
        assert b in full and b not in ablated
    assert "efficiency_gated_fade" in ablated


def test_finalize_applies_bh_fdr():
    import pandas as pd
    nets = {"winner": pd.DataFrame({"net": np.random.default_rng(0).normal(0.5, 1.0, 400)}),
            "null": pd.DataFrame({"net": np.random.default_rng(1).normal(0.0, 1.0, 400)})}
    assert "winner" in finalize_selection(nets, q=0.10)
    assert "null" not in finalize_selection(nets, q=0.10)


def test_run_search_mocked_writer():
    by = _by_sym()

    def fake(parent_src, parent_score, logs, idea, cache_dir, rules=None, caller=None):
        return "def signal(ctx):\n    return ctx.col('vel_pips_h1')\n"

    nodes = run_search(by, symbols=["EURUSD", "GBPUSD"], budget=3, writer=fake, p_recombine=0.0)
    assert len(nodes) >= 3 and all(np.isfinite(n.score) for n in nodes)

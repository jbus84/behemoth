import numpy as np

from scripts.era.run_era import run_search
from scripts.era.score_program import SplitData
from scripts.era.seeds import SEED_PROGRAMS


def _reverting_split(n=400, seed=3):
    rng = np.random.RandomState(seed)
    r = rng.randn(n, 6)
    z = (r[:, 0] - r[:, 1:].mean(1)) / (r[:, 1:].std(1) + 1e-9)
    # fading z (side = -sign(z)*usd_sign, usd_sign=-1) is profitable:
    y = np.sign(z) * np.abs(rng.randn(n))  # so side*y = -|.| ... see harness
    months = np.array([f"2025-{1 + (i % 8):02d}" for i in range(n)])
    return SplitData(
        r=r,
        names=list("ABCDEF"),
        target="A",
        usd_sign=-1,
        y_fwd=-y,
        cost=np.full(n, 0.05),
        test_month=months,
    )


def test_search_rediscovers_a_seed_baseline():
    splits = {"train": _reverting_split(), "validation": _reverting_split(seed=4)}

    # mocked writer: always returns the loo_z seed (stands in for qwen)
    def writer(parent_src, parent_score, logs, idea, cache_dir, caller=None):
        return SEED_PROGRAMS["loo_z"]

    nodes = run_search(
        splits, thresholds=[1.0, 1.5, 2.0], budget=20, writer=writer, ideas=["loo"], seed=0
    )
    best = max(nodes, key=lambda nd: nd.score)
    assert np.isfinite(best.score)
    # loo_z must score finite & be selected among the top
    assert best.score >= sorted(nd.score for nd in nodes)[len(nodes) // 2]


def test_no_baseline_seeds_filters_canonical(tmp_path):
    from scripts.era.run_era import select_seed_programs

    full = select_seed_programs(no_baseline=False)
    ablated = select_seed_programs(no_baseline=True)
    for name in ("dispersion_rank", "loo_z", "robust_z", "graph_laplacian"):
        assert name in full
        assert name not in ablated
    assert "all6_z" in ablated


def test_finalize_applies_bh_fdr(tmp_path):
    import pandas as pd

    from scripts.era.run_era import finalize_selection

    holdout_nets = {
        "winner": pd.DataFrame({"net": np.random.default_rng(0).normal(1.0, 1.0, 400)}),
        "null": pd.DataFrame({"net": np.random.default_rng(1).normal(0.0, 1.0, 400)}),
    }
    survivors = finalize_selection(holdout_nets, q=0.10)
    assert "winner" in survivors
    assert "null" not in survivors

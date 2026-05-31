import numpy as np

from scripts.era_scalp.load_splits import WHITELIST, FairSplitData
from scripts.era_scalp.run_era_fair import finalize_selection, run_search, select_seed_programs


def _data(n=600, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4
    return FairSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid,
        test_month=np.array(["2024-01"] * (n // 2) + ["2024-02"] * (n - n // 2)),
    )


def test_select_seed_programs_ablation():
    full = select_seed_programs(no_baseline=False)
    ablated = select_seed_programs(no_baseline=True)
    for b in ("ewma_denoise_dev", "bounce_reversal_dev", "microprice_imbalance_dev",
              "trailing_anchor_dev"):
        assert b in full and b not in ablated
    assert "ofi_adjusted_dev" in ablated


def test_finalize_applies_bh_fdr():
    cand = {"winner": (0.30, 400), "null": (0.001, 400)}
    survivors = finalize_selection(cand, q=0.10)
    assert "winner" in survivors and "null" not in survivors


def test_run_search_with_mocked_writer():
    splits = {"validation": _data(), "holdout": _data(seed=2)}

    def fake_writer(parent_src, parent_score, logs, idea, cache_dir, rules=None, caller=None):
        return "def fair(ctx):\n    return ctx.col('vel_pips_h1')\n"

    nodes = run_search(splits, symbol="EURUSD", budget=3, writer=fake_writer, p_recombine=0.0)
    assert len(nodes) >= 3
    assert all(np.isfinite(n.score) for n in nodes)

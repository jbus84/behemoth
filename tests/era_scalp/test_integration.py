import numpy as np
import pandas as pd

from scripts.era_scalp.run_era_scalp import finalize_selection, run_search, select_seed_programs
from scripts.era_scalp.score_program import ScalpSplitData


def _split(n=300, seed=0):
    from scripts.era_scalp.load_splits import WHITELIST

    rng = np.random.default_rng(seed)
    return ScalpSplitData(
        X=rng.standard_normal((n, len(WHITELIST))),
        names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float),
        y_fwd=rng.standard_normal(n),
        cost=np.full(n, 0.4),
        test_month=np.array(["2024-01"] * (n // 2) + ["2024-02"] * (n - n // 2)),
    )


def test_select_seed_programs_ablation():
    full = select_seed_programs(no_baseline=False)
    ablated = select_seed_programs(no_baseline=True)
    for b in ("ofi_flow", "ou_sscore", "hawkes_cont", "ofi_multihorizon"):
        assert b in full and b not in ablated
    assert "roll_bounce_fade" in ablated


def test_finalize_applies_bh_fdr():
    holdout_nets = {
        "winner": pd.DataFrame({"net": np.random.default_rng(0).normal(0.5, 1.0, 400)}),
        "null": pd.DataFrame({"net": np.random.default_rng(1).normal(0.0, 1.0, 400)}),
    }
    survivors = finalize_selection(holdout_nets, q=0.10)
    assert "winner" in survivors and "null" not in survivors


def test_run_search_with_mocked_writer():
    splits = {"validation": _split(), "holdout": _split(seed=2)}

    def fake_writer(parent_src, parent_score, logs, idea, cache_dir, rules=None, caller=None):
        return "def signal(ctx):\n    return ctx.col('vel_z_h2')\n"

    nodes = run_search(splits, thresholds=[0.5, 1.0], budget=3,
                       writer=fake_writer, p_recombine=0.0)
    assert len(nodes) >= 3
    assert all(np.isfinite(n.score) for n in nodes)


def test_summarize_rejections_categorizes():
    from scripts.era.puct import Node
    from scripts.era_scalp.run_era_scalp import summarize_rejections

    nodes = [
        Node(payload="a", score=0.2, parent=None, logs="ok"),
        Node(payload="b", score=-1e6, parent=None, logs="causality_probe: non-causal ..."),
        Node(payload="c", score=-1e6, parent=None, logs="exec: timeout"),
        Node(payload="d", score=-1e6, parent=None, logs="static_check: must define signal(ctx)"),
    ]
    h = summarize_rejections(nodes)
    assert h["total"] == 4 and h["rejected"] == 3
    assert h["timeout"] == 1 and h["causality"] == 1 and h["static_or_exec"] == 1

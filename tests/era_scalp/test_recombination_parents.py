import numpy as np

from scripts.era.puct import Node
from scripts.era_scalp.era_engine import _recombination_parents


def _node(score, branch, visits=1):
    return Node(payload="x", score=score, parent=None, visits=visits, branch=branch)


def test_parent_b_is_different_branch():
    nodes = [_node(5.0, "a"), _node(4.0, "a"), _node(1.0, "b")]
    pa, pb = _recombination_parents(nodes, c_branch=0.7, rng=np.random.default_rng(0))
    assert pb.branch != pa.branch


def test_parent_a_diversity_beats_greedy_top_scorer():
    # 'rich' branch saturated (20 nodes incl the global max=5.0); 'fresh' under-explored (1 node).
    # Greedy would pick the score-5.0 'rich' node; the diversity bonus must pick 'fresh'.
    nodes = [_node(5.0, "rich")] + [_node(4.0, "rich") for _ in range(19)] + [_node(0.5, "fresh")]
    pa, _ = _recombination_parents(nodes, c_branch=0.7, rng=np.random.default_rng(0))
    assert pa.branch == "fresh"


def test_single_branch_returns_two_distinct_nodes():
    nodes = [_node(3.0, "a"), _node(2.0, "a")]
    pa, pb = _recombination_parents(nodes, c_branch=0.7, rng=np.random.default_rng(0))
    assert pa is not pb

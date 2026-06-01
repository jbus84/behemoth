import numpy as np

from scripts.era.puct import Node, puct_search, select, select_thompson


def _node(mean, se):
    return Node(payload="x", score=mean, parent=None, mean=mean, se=se)


def test_thompson_favours_dominant_node():
    rng = np.random.default_rng(0)
    nodes = [_node(2.0, 0.1), _node(0.0, 0.1), _node(-1.0, 0.1)]
    picks = [select_thompson(nodes, rng) is nodes[0] for _ in range(200)]
    assert sum(picks) > 180  # clear winner dominates


def test_thompson_sometimes_explores_uncertain_underdog():
    rng = np.random.default_rng(0)
    nodes = [_node(1.0, 0.05), _node(0.5, 3.0)]  # underdog has high uncertainty
    picks = [select_thompson(nodes, rng) is nodes[1] for _ in range(200)]
    assert 0 < sum(picks) < 200  # explored sometimes, not always


def test_thompson_zero_se_uses_mean():
    rng = np.random.default_rng(1)
    nodes = [_node(1.0, 0.0), _node(2.0, 0.0)]
    assert all(select_thompson(nodes, rng) is nodes[1] for _ in range(20))


def test_puct_search_accepts_select_fn():
    root = Node(payload=0, score=0.0, parent=None, mean=0.0, se=1.0)
    def expand(parent):
        return Node(payload=1, score=1.0, parent=parent, mean=1.0, se=1.0)
    rng = np.random.default_rng(2)
    nodes = puct_search([root], expand, budget=5,
                        select_fn=lambda ns, c: select_thompson(ns, rng))
    assert len(nodes) == 6  # root + 5 expansions

import numpy as np
from scripts.era.puct import Node, puct_search

def test_search_improves_and_keeps_all_nodes():
    # toy: a node's "program" is a float x; score = -(x-3)**2; child nudges toward 3
    rng = np.random.RandomState(0)
    def expand(parent):
        x = parent.payload + rng.uniform(-1, 1)
        return Node(payload=x, score=-(x - 3.0) ** 2, parent=parent)
    root = Node(payload=0.0, score=-(0 - 3.0) ** 2, parent=None)
    nodes = puct_search([root], expand, budget=80, c_puct=1.0, seed=0)
    assert len(nodes) == 81  # root + 80 expansions, nothing pruned
    best = max(nodes, key=lambda n: n.score)
    assert best.score > root.score  # search made progress

def test_selection_prefers_high_rank_or_low_visits():
    # a visited high scorer vs an unvisited node: exploration term must matter
    from scripts.era.puct import select
    a = Node(payload=1, score=1.0, parent=None); a.visits = 50
    b = Node(payload=2, score=0.9, parent=None); b.visits = 1
    chosen = select([a, b], c_puct=1.0)
    assert chosen is b  # low-visit node wins on exploration despite lower score

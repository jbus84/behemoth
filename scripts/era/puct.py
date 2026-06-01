from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Node:
    payload: object  # program source (or toy value)
    score: float  # validation TaskScore
    parent: Node | None
    visits: int = 1
    logs: str = ""
    children: list = field(default_factory=list)
    mean: float = 0.0
    se: float = 0.0


def _rank_scores(nodes: list[Node]) -> dict[int, float]:
    order = sorted(range(len(nodes)), key=lambda i: nodes[i].score)
    out = {}
    for rank, i in enumerate(order):
        out[i] = rank / max(1, len(nodes) - 1)  # 0..1, higher score -> higher rank
    return out


def select(nodes: list[Node], c_puct: float) -> Node:
    ranks = _rank_scores(nodes)
    n_total = sum(n.visits for n in nodes)
    p = 1.0 / len(nodes)  # uniform prior
    best_i, best_v = 0, -1e18
    for i, nd in enumerate(nodes):
        explore = c_puct * p * np.sqrt(n_total) / (1 + nd.visits)
        v = ranks[i] + explore
        if v > best_v:
            best_v, best_i = v, i
    return nodes[best_i]


def select_thompson(nodes: list[Node], rng) -> Node:
    """Thompson sampling: draw from each node's edge posterior N(mean, se), pick the argmax draw."""
    best_i, best_draw = 0, -1e18
    for i, nd in enumerate(nodes):
        draw = nd.mean if nd.se <= 0 else float(rng.normal(nd.mean, nd.se))
        if draw > best_draw:
            best_draw, best_i = draw, i
    return nodes[best_i]


def puct_search(
    initial_nodes: list[Node], expand_fn, budget: int, c_puct: float = 1.0, seed: int = 0,
    select_fn=None,
) -> list[Node]:
    np.random.seed(seed)
    nodes = list(initial_nodes)
    chooser = select_fn if select_fn is not None else select
    for _ in range(budget):
        parent = chooser(nodes, c_puct)
        child = expand_fn(parent)
        parent.children.append(child)
        nodes.append(child)
        a = child.parent
        while a is not None:
            a.visits += 1
            a = a.parent
    return nodes

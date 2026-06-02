from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Node:
    payload: object  # program source (or spec dict)
    score: float  # validation TaskScore
    parent: Node | None
    visits: int = 1
    logs: str = ""
    children: list = field(default_factory=list)
    mean: float = 0.0
    se: float = 0.0
    # Branch-aware fields (optional — set by branch-aware drivers)
    branch: str | None = None  # literature branch tag, e.g. "mean_reversion_gate"


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


def _branch_counts(nodes: list[Node]) -> dict[str | None, int]:
    """Count how many NODES (distinct programs) each branch has produced.

    This reflects conceptual coverage: a branch with 30 nodes has been explored
    more thoroughly than one with 3 nodes, regardless of how many times those
    nodes were selected as parents by PUCT.
    """
    counts: dict[str | None, int] = {}
    for nd in nodes:
        b = nd.branch
        counts[b] = counts.get(b, 0) + 1
    return counts


def _normalised_scores(nodes: list[Node]) -> dict[int, float]:
    """Map raw scores to [0,1] using min-max normalisation over the current frontier."""
    scores = [nd.score for nd in nodes]
    lo, hi = min(scores), max(scores)
    span = hi - lo
    if span <= 0:
        return {i: 1.0 for i in range(len(nodes))}
    return {i: (nodes[i].score - lo) / span for i in range(len(nodes))}


def select_diversity(nodes: list[Node], c_puct: float = 1.0,
                     c_branch: float = 0.5, rng=None) -> Node:
    """Branch-aware UCB selection: bonus for under-explored branches.

    Uses min-max normalised scores instead of rank scores so that the diversity
    bonus can meaningfully nudge under-represented branches without requiring
    extreme c_branch values.

    Parameters
    ----------
    c_puct : float
        Standard PUCT exploration constant.
    c_branch : float
        Branch diversity weight.  0 = score-only UCB (no diversity bonus).
    rng : np.random.Generator | None
        Unused in this selector (kept for API consistency with select_thompson).
    """
    norm = _normalised_scores(nodes)
    n_total = sum(n.visits for n in nodes)
    branch_counts = _branch_counts(nodes)
    total_nodes = sum(branch_counts.values())
    best_i, best_v = 0, -1e18
    for i, nd in enumerate(nodes):
        # Standard PUCT explore term
        p = 1.0 / len(nodes)
        explore = c_puct * p * np.sqrt(n_total) / (1 + nd.visits)
        # Branch diversity bonus: under-explored branches get a boost
        branch_n = branch_counts.get(nd.branch, 1)
        diversity = c_branch * np.sqrt(total_nodes) / (1 + branch_n)
        v = norm[i] + explore + diversity
        if v > best_v:
            best_v, best_i = v, i
    return nodes[best_i]


def select_diversity_with_priors(nodes: list[Node], c_puct: float = 1.0,
                                  c_branch: float = 0.5,
                                  branch_priors: dict[str, float] | None = None,
                                  rng=None) -> Node:
    """Branch-aware UCB selection with Level-1 branch priors.

    After running many small PUCT trees (Level 1), we compute a prior score
    for each branch based on its average performance.  In Level 2, nodes from
    high-prior branches get their normalised score multiplied by the prior,
    focusing deep search on branches that Level 1 showed promise while still
    allowing exploration of weaker branches via the diversity bonus.

    Parameters
    ----------
    branch_priors : dict[str, float] | None
        Mapping branch -> prior weight (typically in [0.5, 2.0]).
        1.0 = neutral.  Higher = branch was strong in Level 1.
    """
    norm = _normalised_scores(nodes)
    n_total = sum(n.visits for n in nodes)
    branch_counts = _branch_counts(nodes)
    total_nodes = sum(branch_counts.values())
    best_i, best_v = 0, -1e18
    for i, nd in enumerate(nodes):
        p = 1.0 / len(nodes)
        explore = c_puct * p * np.sqrt(n_total) / (1 + nd.visits)
        branch_n = branch_counts.get(nd.branch, 1)
        diversity = c_branch * np.sqrt(total_nodes) / (1 + branch_n)
        # Prior boost: multiply normalised score by branch prior from Level 1
        prior = branch_priors.get(nd.branch, 1.0) if branch_priors else 1.0
        v = norm[i] * prior + explore + diversity
        if v > best_v:
            best_v, best_i = v, i
    return nodes[best_i]


def compute_branch_priors(all_nodes_list: list[list[Node]],
                          min_prior: float = 0.5,
                          max_prior: float = 2.0) -> dict[str, float]:
    """Compute branch priors from Level 1 (many small trees).

    Uses the *mean validation score* of all valid nodes per branch across
    all trees.  Branches with higher average scores get higher priors.

    Parameters
    ----------
    all_nodes_list : list[list[Node]]
        One list of nodes per Level 1 tree.
    min_prior, max_prior : float
        Range to scale priors into.  Neutral = 1.0.
    """
    branch_scores: dict[str, list[float]] = {}
    for nodes in all_nodes_list:
        for nd in nodes:
            if nd.score > -1e6 + 1:
                b = nd.branch or "unknown"
                branch_scores.setdefault(b, []).append(nd.score)

    if not branch_scores:
        return {}

    branch_means = {b: float(np.mean(scores)) for b, scores in branch_scores.items()}
    lo, hi = min(branch_means.values()), max(branch_means.values())
    span = hi - lo
    if span <= 0:
        return {b: 1.0 for b in branch_means}

    priors = {}
    for b, mean_score in branch_means.items():
        normalized = (mean_score - lo) / span  # 0..1
        priors[b] = min_prior + normalized * (max_prior - min_prior)
    return priors


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

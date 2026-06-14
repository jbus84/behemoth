#!/usr/bin/env python3
"""Dry-run demonstration of branch-aware PUCT with all 18 seeds and 12 branches.

No LLM calls — just the selection/recombination mechanics, to show how diversity
bonus + cross-branch recombination + cross-branch proposals work together.
"""

from __future__ import annotations

import numpy as np

from scripts.era.puct import Node, select_diversity
from scripts.era_scalp.fade_seeds import (
    CROSS_BRANCH_INDEX,
    FADE_SEED_PROGRAMS,
    SEED_BRANCH_TAGS,
)


# ── Fake scorer (deterministic, for demo only) ──────────────────────────────
class FakeScorer:
    """Assigns scores based on branch 'quality' plus noise.

    The idea: some branches (e.g. mean_reversion_gate) start with higher scores,
    while new branches (seasonality, asymmetric_vol) start lower.  The diversity
    bonus should still pick them occasionally.
    """

    BRANCH_BASE = {
        "baseline": 0.05,
        "mean_reversion_gate": 0.12,
        "regime_switching": 0.08,
        "empirical_direction": 0.10,
        "adaptive_estimation": 0.07,
        "microstructure_gate": 0.06,
        "liquidity_gate": 0.06,
        "transient_impact": 0.04,
        "jump_aware": 0.04,
        "flow_intensity": 0.03,
        "asymmetric_vol": 0.03,
        "seasonality": 0.02,
        "hybrid": 0.09,
    }

    def __init__(self, seed=42):
        self.rng = np.random.default_rng(seed)

    def score(self, src: str, branch: str | None) -> tuple[float, float, float, str]:
        base = self.BRANCH_BASE.get(branch or "baseline", 0.05)
        noise = self.rng.normal(0, 0.02)
        v = base + noise
        return v, v, 0.01, ""


# ── Demo expand function ────────────────────────────────────────────────────
def demo_expand(parent: Node, all_nodes: list[Node], scorer: FakeScorer,
                 rng: np.random.Generator,
                 p_recombine: float = 0.3,
                 p_cross_branch: float = 0.2) -> tuple[Node, str]:
    """Return (child_node, action_description)."""
    action: str
    child_branch: str

    if rng.random() < p_recombine and len(all_nodes) >= 2:
        # Recombine: pick top-2 from different branches
        cands = sorted(all_nodes, key=lambda n: n.score, reverse=True)
        parent_a = cands[0]
        parent_b = next(
            (n for n in cands[1:] if n.branch != parent_a.branch), cands[1]
        )
        branch_a = parent_a.branch or "baseline"
        branch_b = parent_b.branch or "baseline"

        if branch_a != branch_b and (branch_a, branch_b) in CROSS_BRANCH_INDEX:
            cross_text = "cross-branch recombination"
        else:
            cross_text = "same-branch recombination"

        action = f"RECOMBINE {parent_a.branch} + {parent_b.branch} ({cross_text})"
        child_branch = "hybrid"
    else:
        # Propose: same-branch or cross-branch
        branch_pool = list({n.branch for n in all_nodes if n.branch is not None})
        if rng.random() < p_cross_branch and len(branch_pool) > 1:
            other = [b for b in branch_pool if b != parent.branch]
            target = rng.choice(other)
            action = f"PROPOSE cross-branch jump: {parent.branch} -> {target}"
            child_branch = target
        else:
            action = f"PROPOSE in-branch ({parent.branch})"
            child_branch = parent.branch

    v, mean, se, lg = scorer.score("", child_branch)
    child = Node(
        payload="", score=v, parent=parent, logs=lg,
        mean=mean, se=se, branch=child_branch,
    )
    return child, action


# ── Main demo ───────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("BRANCH-AWARE PUCT DRY RUN")
    print("18 seeds | 12 branches | diversity selection + cross-branch ops")
    print("=" * 70)

    scorer = FakeScorer(seed=42)
    rng = np.random.default_rng(7)
    nprng = np.random.default_rng(7)

    # 1. Initialise forest
    forest: list[Node] = []
    for name, src in FADE_SEED_PROGRAMS.items():
        v, mean, se, lg = scorer.score(src, SEED_BRANCH_TAGS.get(name))
        forest.append(Node(
            payload=src, score=v, parent=None, logs=lg,
            mean=mean, se=se, branch=SEED_BRANCH_TAGS.get(name, "baseline"),
        ))

    all_nodes = list(forest)
    print(f"\nInitial forest: {len(forest)} seeds")
    _print_branch_table(all_nodes)

    # 2. Run PUCT iterations
    budget = 20
    print(f"\nRunning {budget} expansions with select_diversity (c_puct=1.0, c_branch=0.5)...\n")
    print(f"{'Iter':<5} {'Selected branch':<25} {'Action':<50} {'New score':<10}")
    print("-" * 95)

    for i in range(1, budget + 1):
        parent = select_diversity(all_nodes, c_puct=1.0, c_branch=0.5, rng=nprng)
        child, action = demo_expand(
            parent, all_nodes, scorer, rng,
            p_recombine=0.3, p_cross_branch=0.2,
        )
        all_nodes.append(child)
        # Back-propagate visits
        a = child.parent
        while a is not None:
            a.visits += 1
            a = a.parent

        print(f"{i:<5} {parent.branch or '—':<25} {action:<50} {child.score:+.3f}")

    # 3. Final summary
    print("\n" + "=" * 70)
    print("FINAL BRANCH DISTRIBUTION")
    print("=" * 70)
    _print_branch_table(all_nodes)

    print("\n" + "=" * 70)
    print("TOP 10 NODES BY SCORE")
    print("=" * 70)
    for nd in sorted(all_nodes, key=lambda n: n.score, reverse=True)[:10]:
        tag = "SEED" if nd.parent is None else "EVOLVED"
        print(f"  {tag:<7} [{nd.branch or '—':<22}] score={nd.score:+.3f}  visits={nd.visits}")

    # 4. Diversity effect demonstration
    print("\n" + "=" * 70)
    print("DIVERSITY BONUS EFFECT")
    print("=" * 70)
    print("For each branch, showing:  nodes  |  max score  |  diversity bonus")
    from collections import Counter
    counts = Counter(n.branch for n in all_nodes if n.branch is not None)
    total = sum(counts.values())
    for branch, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        branch_nodes = [n for n in all_nodes if n.branch == branch]
        max_score = max(n.score for n in branch_nodes)
        diversity = 0.5 * np.sqrt(total) / (1 + cnt)
        print(f"  {branch:<25}  nodes={cnt:<3}  max={max_score:+.3f}  diversity_bonus={diversity:.3f}")


def _print_branch_table(nodes: list[Node]):
    from collections import Counter
    counts = Counter(n.branch for n in nodes if n.branch is not None)
    print(f"  {'Branch':<25} {'Nodes':>6}")
    print("  " + "-" * 33)
    for branch, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {branch:<25} {cnt:>6}")
    print(f"  {'TOTAL':<25} {sum(counts.values()):>6}")


if __name__ == "__main__":
    main()

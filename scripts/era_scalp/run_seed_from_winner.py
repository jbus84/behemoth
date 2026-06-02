#!/usr/bin/env python3
"""Seed-from-winner ERA search: start with the best evolved program and explore refinements."""

import argparse
import random
from pathlib import Path

import numpy as np

from scripts.era.llm import propose_branch_program, recombine_branch_program
from scripts.era.puct import Node, puct_search, select_diversity
from scripts.era_scalp.bayes_edge import edge_verdict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_aware_score import GRID_H, GRID_Q, CostAwarePerSymbolScorer
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.fade_seeds import (
    CROSS_BRANCH_INDEX,
    RICH_TEMPLATES,
    SEED_BRANCH_TAGS,
)
from scripts.era_scalp.load_splits import _pip_size, build_trade_splits
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.trade_harness import evaluate_trades


def run_search(splits, symbol, budget, seed=0, cache_dir="/tmp/era_eur_cache",
               p_recombine=0.25, p_cross_branch=0.35, c_branch=0.7,
               branch_depth_limit=3, winner_src: str | None = None,
               winner_branch: str = "regime_switching"):
    """Branch-aware ERA-PUCT search seeded from a winning program.

    If winner_src is provided, it replaces the seed library as the starting point.
    The LLM is tasked with refining/improving this specific program.
    """
    scorer = CostAwarePerSymbolScorer(splits, symbol)
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)

    if winner_src is None:
        raise ValueError("winner_src is required for seed-from-winner search")

    # Score the winner to establish baseline
    v, mean, se, lg = scorer.score(winner_src, "validation")
    print(f"[seed-from-winner] baseline val={v:+.3f} mean={mean:.3f} se={se:.3f}")

    # Build single-node forest with the winner
    winner_node = Node(
        payload=winner_src, score=v, parent=None, logs=lg,
        mean=mean, se=se, branch=winner_branch,
    )
    forest = [winner_node]
    all_nodes = list(forest)

    # Also include original seeds for branch diversity
    from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS
    for name, src in FADE_SEED_PROGRAMS.items():
        # Skip if identical to winner
        if src.strip() == winner_src.strip():
            continue
        v2, mean2, se2, lg2 = scorer.score(src, "validation")
        branch = SEED_BRANCH_TAGS.get(name, "baseline")
        forest.append(
            Node(payload=src, score=v2, parent=None, logs=lg2,
                 mean=mean2, se=se2, branch=branch)
        )
        all_nodes.append(forest[-1])

    branch_pool = list(set(n.branch for n in all_nodes if n.branch is not None))

    def _branch_template(branch: str | None) -> str:
        return RICH_TEMPLATES.get(branch or "baseline", RICH_TEMPLATES["baseline"])

    _last_branch: str | None = None
    _branch_depth: int = 0

    def expand(parent: Node) -> Node:
        nonlocal _last_branch, _branch_depth

        if rng.random() < p_recombine and len(all_nodes) >= 2:
            cands = sorted(all_nodes, key=lambda n: n.score, reverse=True)
            parent_a = cands[0]
            parent_b = next(
                (n for n in cands[1:] if n.branch != parent_a.branch), cands[1]
            )
            branch_a = parent_a.branch or "baseline"
            branch_b = parent_b.branch or "baseline"

            if branch_a != branch_b and (branch_a, branch_b) in CROSS_BRANCH_INDEX:
                cross_text = CROSS_BRANCH_INDEX[(branch_a, branch_b)]
            else:
                cross_text = (
                    f"Combine these two programs. Parent A is from the {branch_a} branch; "
                    f"Parent B is from the {branch_b} branch."
                )
            child_src = recombine_branch_program(
                parent_a.payload, parent_a.score, branch_a,
                parent_b.payload, parent_b.score, branch_b,
                cross_text, cache_dir=cache_dir,
            )
            child_branch = branch_a
            _last_branch = child_branch
            _branch_depth = 0
        else:
            force_jump = (
                _last_branch == parent.branch
                and _branch_depth >= branch_depth_limit
                and len(branch_pool) > 1
            )
            if force_jump or (rng.random() < p_cross_branch and len(branch_pool) > 1):
                other_branches = [b for b in branch_pool if b != parent.branch]
                target_branch = rng.choice(other_branches) if other_branches else parent.branch
            else:
                target_branch = parent.branch

            template = _branch_template(target_branch)
            child_src = propose_branch_program(
                parent.payload, parent.score, parent.logs,
                branch=target_branch or "baseline",
                rich_template=template,
                cache_dir=cache_dir,
            )
            child_branch = target_branch

            if _last_branch == child_branch:
                _branch_depth += 1
            else:
                _last_branch = child_branch
                _branch_depth = 1

        v, mean, se, lg = scorer.score(child_src, "validation")
        child = Node(
            payload=child_src, score=v, parent=parent, logs=lg,
            mean=mean, se=se, branch=child_branch,
        )
        all_nodes.append(child)
        return child

    _expansion_count = 0
    def _expand_logged(parent: Node) -> Node:
        nonlocal _expansion_count
        _expansion_count += 1
        child = expand(parent)
        if _expansion_count % 10 == 0 or _expansion_count == budget:
            valid = [n for n in all_nodes if n.score > -1e6 + 1]
            best = max((n.score for n in valid), default=float("-inf"))
            branches = {}
            for n in all_nodes:
                b = n.branch or "unknown"
                branches[b] = branches.get(b, 0) + 1
            print(f"[ERA progress] expansions={_expansion_count}/{budget} nodes={len(all_nodes)} "
                  f"valid={len(valid)} best_score={best:.3f} branches={branches}")
        return child

    def _select_fn(ns, c):
        return select_diversity(ns, c_puct=c, c_branch=c_branch, rng=nprng)

    return puct_search(forest, _expand_logged, budget=budget, c_puct=1.0, seed=seed, select_fn=_select_fn)


def holdout_verdict(src, split_holdout, symbol):
    """Net-of-realistic-cost EUR holdout posterior at the best-by-(q,h) cell."""
    d = split_holdout
    ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
    sig, err, _ = run_program(src, ctx, required_fn="signal")
    if err is not None:
        return None
    cost = realistic_cost(d.spread_pips)
    pip = _pip_size(symbol)
    best = None
    for q in GRID_Q:
        for h in GRID_H:
            frame = evaluate_trades(sig, d.mid, cost, d.test_month, pip, q, h)
            if len(frame) < 50:
                continue
            try:
                post = edge_verdict({symbol: frame})
            except ValueError:
                continue
            p = post.pooled["p_positive"]
            if best is None or p > best["p_positive"]:
                best = {**post.pooled, "q": q, "h": h, "n_trades": int(len(frame)),
                        "raw_mean": float(frame["net"].mean())}
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="/tmp/era_eur/seed_from_winner_verdict.md")
    ap.add_argument("--winner", required=True, help="path to the winning program .py file")
    ap.add_argument("--winner-branch", default="regime_switching")
    ap.add_argument("--c-branch", type=float, default=0.7)
    ap.add_argument("--p-recombine", type=float, default=0.25)
    ap.add_argument("--p-cross-branch", type=float, default=0.35)
    ap.add_argument("--branch-depth-limit", type=int, default=3)
    args = ap.parse_args()

    winner_src = Path(args.winner).read_text()
    sp = build_trade_splits(args.symbol, Path(args.tv_dir) / f"{args.symbol}_100tick_velocity.parquet",
                            embargo=max(GRID_H))
    nodes = run_search(sp, args.symbol, budget=args.budget, seed=args.seed,
                       p_recombine=args.p_recombine, p_cross_branch=args.p_cross_branch,
                       c_branch=args.c_branch, branch_depth_limit=args.branch_depth_limit,
                       winner_src=winner_src, winner_branch=args.winner_branch)

    seen_payloads: set[str] = set()
    unique_ranked = []
    for nd in sorted([n for n in nodes if n.score > -1e6 + 1], key=lambda n: n.score, reverse=True):
        if nd.payload not in seen_payloads:
            seen_payloads.add(nd.payload)
            unique_ranked.append(nd)

    lines = [f"# Seed-from-winner PUCT verdict — {args.symbol} (budget={args.budget})\n"]
    for nd in unique_ranked[:5]:
        hv = holdout_verdict(nd.payload, sp["holdout"], args.symbol)
        tag = "SEED" if nd.parent is None else "evolved"
        branch_tag = f"[{nd.branch}]" if nd.branch else ""
        if hv:
            lines.append(f"- [{tag}] {branch_tag} val={nd.score:+.3f} | holdout P={hv['p_positive']:.3f} "
                         f"raw={hv['raw_mean']:+.3f} (q{hv['q']} h{hv['h']} n={hv['n_trades']})")
        else:
            lines.append(f"- [{tag}] {branch_tag} val={nd.score:+.3f} | holdout: program error")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

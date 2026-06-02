from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from scripts.era.llm import (
    propose_branch_program,
    recombine_branch_program,
)
from scripts.era.puct import Node, puct_search, select_diversity, select_thompson
from scripts.era_scalp.bayes_edge import edge_verdict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_aware_score import GRID_H, GRID_Q, CostAwarePerSymbolScorer
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.fade_seeds import (
    CROSS_BRANCH_INDEX,
    FADE_SEED_PROGRAMS,
    RICH_TEMPLATES,
    SEED_BRANCH_TAGS,
)
from scripts.era_scalp.load_splits import _pip_size, build_trade_splits
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.trade_harness import evaluate_trades

SYMBOL_DEFAULT = "EURUSD"
TRIVIAL_ROOT = (
    "def signal(ctx):\n"
    "    return ctx.col('vel_pips_h1') * 0.0 + ctx.col('vel_pips_h1')\n"
)


def run_search(splits, symbol, budget, select_policy="diversity", seed=0,
               cache_dir="/tmp/era_eur_cache", p_recombine=0.15, p_cross_branch=0.35,
               c_branch=1.2, seed_programs=None):
    """Branch-aware ERA-PUCT search.

    Parameters
    ----------
    select_policy : str
        "thompson" | "rank" | "diversity"
        "diversity" adds a branch-exploration bonus so under-sampled literature
        branches (e.g. regime_switching) get selected even when their raw score
        is below the current best mean_reversion_gate node.
    p_recombine : float
        Probability of recombining two parent nodes instead of mutating one.
        Default 0.15 (low: explore branches individually before combining).
    p_cross_branch : float
        When doing a *propose* (not recombine), probability of forcing a jump
        to a different branch's rich template instead of staying in the parent's
        branch.  Default 0.35 (high: actively explore new branches).
    c_branch : float
        Diversity bonus weight in select_diversity.  Higher = stronger preference
        for under-explored branches.  Default 1.2.
    """
    scorer = CostAwarePerSymbolScorer(splits, symbol)
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)

    if seed_programs is None:
        seed_programs = FADE_SEED_PROGRAMS

    # Build forest with branch tags
    forest = []
    for name, src in seed_programs.items():
        v, mean, se, lg = scorer.score(src, "validation")
        branch = SEED_BRANCH_TAGS.get(name, "baseline")
        forest.append(
            Node(payload=src, score=v, parent=None, logs=lg, mean=mean, se=se, branch=branch)
        )
    all_nodes = list(forest)

    # Collect branch list for cross-branch jumps
    branch_pool = list(set(n.branch for n in all_nodes if n.branch is not None))

    def _branch_template(branch: str | None) -> str:
        return RICH_TEMPLATES.get(branch or "baseline", RICH_TEMPLATES["baseline"])

    def expand(parent: Node) -> Node:
        # Decide: recombine vs propose
        if rng.random() < p_recombine and len(all_nodes) >= 2:
            cands = sorted(all_nodes, key=lambda n: n.score, reverse=True)
            # Prefer top-2 from different branches for recombination
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
            # Assign recombination child to the higher-scoring parent's branch
            # so it contributes to branch coverage instead of creating a parasitic
            # catch-all "hybrid" branch.
            child_branch = branch_a
        else:
            # Propose: stay in branch or jump to a different branch
            if rng.random() < p_cross_branch and len(branch_pool) > 1:
                # Force a cross-branch proposal: pick a different branch's template
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

        v, mean, se, lg = scorer.score(child_src, "validation")
        child = Node(
            payload=child_src, score=v, parent=parent, logs=lg,
            mean=mean, se=se, branch=child_branch,
        )
        all_nodes.append(child)
        return child

    # Selection function
    if select_policy == "thompson":
        def _select_fn(ns, c):
            return select_thompson(ns, nprng)
    elif select_policy == "diversity":
        def _select_fn(ns, c):
            return select_diversity(ns, c_puct=c, c_branch=c_branch, rng=nprng)
    else:
        _select_fn = None  # default rank-based select

    return puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed, select_fn=_select_fn)


def holdout_verdict(src, split_holdout, symbol):
    """Net-of-realistic-cost EUR holdout posterior at the best-by-(q,h) cell. None on program error."""
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
    ap.add_argument("--symbol", default=SYMBOL_DEFAULT)
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--budget", type=int, default=40)
    ap.add_argument("--policy", default="diversity",
                    choices=["thompson", "rank", "diversity"],
                    help="selection policy: thompson=posterior sampling, rank=UCB, "
                         "diversity=branch-aware UCB with exploration bonus")
    ap.add_argument("--no-seeds", action="store_true", help="rediscovery control")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="/tmp/era_eur/verdict.md")
    ap.add_argument("--c-branch", type=float, default=1.2,
                    help="diversity bonus weight for branch-aware selection (default 1.2)")
    ap.add_argument("--p-recombine", type=float, default=0.15,
                    help="probability of cross-parent recombination vs single-parent propose (default 0.15)")
    ap.add_argument("--p-cross-branch", type=float, default=0.35,
                    help="probability of jumping to a different branch's template on propose (default 0.35)")
    args = ap.parse_args()
    sp = build_trade_splits(args.symbol, Path(args.tv_dir) / f"{args.symbol}_100tick_velocity.parquet",
                            embargo=max(GRID_H))
    seed_programs = {"_root": TRIVIAL_ROOT} if args.no_seeds else None
    nodes = run_search(sp, args.symbol, budget=args.budget, select_policy=args.policy,
                       seed=args.seed, seed_programs=seed_programs,
                       p_recombine=args.p_recombine, p_cross_branch=args.p_cross_branch,
                       c_branch=args.c_branch)
    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=lambda n: n.score, reverse=True)
    lines = [f"# Cost-aware PUCT verdict — {args.symbol} (policy={args.policy}, "
             f"seeds={'no' if args.no_seeds else 'yes'}, budget={args.budget})\n"]
    for nd in ranked[:5]:
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

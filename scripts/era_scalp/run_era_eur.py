from __future__ import annotations

import argparse
import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from scripts.era.llm import (
    propose_branch_program,
    recombine_branch_program,
)
from scripts.era.puct import Node, puct_search, select_diversity, select_thompson
from scripts.era_scalp.bayes_edge import edge_verdict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_aware_score import GRID_H, GRID_H_SHORT, GRID_Q, CostAwarePerSymbolScorer
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.fade_seeds import (
    CROSS_BRANCH_INDEX as FADE_CROSS_BRANCH_INDEX,
    FADE_SEED_PROGRAMS,
    RICH_TEMPLATES as FADE_RICH_TEMPLATES,
    SEED_BRANCH_TAGS as FADE_SEED_BRANCH_TAGS,
)
from scripts.era_scalp.fair_seeds import (
    CROSS_BRANCH_INDEX as FAIR_CROSS_BRANCH_INDEX,
    FAIR_SEED_PROGRAMS,
    RICH_TEMPLATES as FAIR_RICH_TEMPLATES,
    SEED_BRANCH_TAGS as FAIR_SEED_BRANCH_TAGS,
)
from scripts.era_scalp.load_splits import _pip_size, build_trade_splits
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.trade_harness import evaluate_fair_price_trades, evaluate_trades

class WinnerArchive:
    """Persist evolved programs that score above a threshold.

    Programs are written to data/era_winners/{symbol}/{timestamp}_{score}_{branch}_{hash}.py
    with YAML frontmatter containing score, holdout stats, and parent lineage.
    """

    def __init__(self, symbol: str, threshold: float = -0.5,
                 root: Path | None = None):
        self.symbol = symbol
        self.threshold = threshold
        self.root = root or Path("data/era_winners")
        self.dir = self.root / symbol
        self.dir.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()

    def _key(self, src: str) -> str:
        return hashlib.sha256(src.encode()).hexdigest()[:12]

    def save(self, src: str, score: float, mean: float, se: float,
             branch: str | None, parent: Node | None,
             holdout: dict | None = None) -> Path | None:
        """Save program if score > threshold and not already saved."""
        if score <= self.threshold:
            return None
        key = self._key(src)
        if key in self._seen:
            return None
        self._seen.add(key)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}_val{score:+.3f}_{branch or 'unknown'}_{key}.py"
        path = self.dir / fname

        meta = {
            "symbol": self.symbol,
            "score": float(score),
            "mean": float(mean),
            "se": float(se),
            "branch": branch,
            "parent_score": float(parent.score) if parent else None,
            "parent_branch": parent.branch if parent else None,
            "holdout": holdout,
            "timestamp": ts,
        }

        lines = [
            '"""',
            json.dumps(meta, indent=2, default=str),
            '"""',
            "",
            src,
        ]
        path.write_text("\n".join(lines))
        print(f"[archive] saved {path}")
        return path


SYMBOL_DEFAULT = "EURUSD"
TRIVIAL_ROOT = (
    "def signal(ctx):\n"
    "    return ctx.col('vel_pips_h1') * 0.0 + ctx.col('vel_pips_h1')\n"
)

FAIR_TRIVIAL_ROOT = (
    "def estimate_fair(ctx):\n"
    "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.02\n"
    "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
    "    ew = np.empty(n); acc = p[0]\n"
    "    for i in range(n):\n"
    "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
    "    return ew\n"
)


def run_search(splits, symbol, budget, select_policy="diversity", seed=0,
               cache_dir="/tmp/era_eur_cache", p_recombine=0.25, p_cross_branch=0.35,
               c_branch=0.7, branch_depth_limit=3, seed_programs=None, archive=None,
               fair_price_mode: bool = False):
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
        Default 0.25 (moderate: enough cross-branch hybrids to find novel
        recombinations without overwhelming single-branch refinement).
    p_cross_branch : float
        When doing a *propose* (not recombine), probability of forcing a jump
        to a different branch's rich template instead of staying in the parent's
        branch.  Default 0.35 (high: actively explore new branches).
    c_branch : float
        Diversity bonus weight in select_diversity.  Higher = stronger preference
        for under-explored branches.  Default 0.7 (tuned: prevents over-exploring
        a branch with marginal early advantage while still giving new branches
        a fair shot).
    branch_depth_limit : int
        If the same branch produces this many consecutive children, force the
        next *propose* to jump to a different branch.  This prevents
        parameter-sweeping paralysis.  Default 3.
    fair_price_mode : bool
        If True, programs define `estimate_fair(ctx)` and the harness trades on
        deviations from fair price using short horizons (h=1-20 bars).
    """
    scorer = CostAwarePerSymbolScorer(splits, symbol, fair_price_mode=fair_price_mode)
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)

    if seed_programs is None:
        seed_programs = FAIR_SEED_PROGRAMS if fair_price_mode else FADE_SEED_PROGRAMS

    seed_branch_tags = FAIR_SEED_BRANCH_TAGS if fair_price_mode else FADE_SEED_BRANCH_TAGS
    rich_templates = FAIR_RICH_TEMPLATES if fair_price_mode else FADE_RICH_TEMPLATES
    cross_branch_index = FAIR_CROSS_BRANCH_INDEX if fair_price_mode else FADE_CROSS_BRANCH_INDEX

    # Build forest with branch tags
    forest = []
    for name, src in seed_programs.items():
        v, mean, se, lg = scorer.score(src, "validation")
        branch = seed_branch_tags.get(name, "baseline")
        forest.append(
            Node(payload=src, score=v, parent=None, logs=lg, mean=mean, se=se, branch=branch)
        )
    all_nodes = list(forest)

    # Collect branch list for cross-branch jumps
    branch_pool = list(set(n.branch for n in all_nodes if n.branch is not None))

    def _branch_template(branch: str | None) -> str:
        return rich_templates.get(branch or "baseline", rich_templates["baseline"])

    # Track consecutive expansions within the same branch to prevent parameter-sweep paralysis.
    _last_branch: str | None = None
    _branch_depth: int = 0

    def expand(parent: Node) -> Node:
        nonlocal _last_branch, _branch_depth

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

            if branch_a != branch_b and (branch_a, branch_b) in cross_branch_index:
                cross_text = cross_branch_index[(branch_a, branch_b)]
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
            _last_branch = child_branch
            _branch_depth = 0  # recombination resets depth (it's inherently cross-concept)
        else:
            # Propose: stay in branch or jump to a different branch
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

            # Update branch-depth tracker
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
        if archive is not None and v > -1e6 + 1:
            archive.save(child_src, v, mean, se, child_branch, parent, None)
        return child

    # Progress logging
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
            print(f"[ERA progress] expansions={_expansion_count}/{budget}  nodes={len(all_nodes)}  "
                  f"valid={len(valid)}  best_score={best:.3f}  branches={branches}")
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

    return puct_search(forest, _expand_logged, budget=budget, c_puct=1.0, seed=seed, select_fn=_select_fn)


def holdout_verdict(src, split_holdout, symbol, fair_price_mode: bool = False):
    """Net-of-realistic-cost EUR holdout posterior at the best-by-(q,h) cell. None on program error."""
    d = split_holdout
    ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
    required_fn = "estimate_fair" if fair_price_mode else "signal"
    out, err, _ = run_program(src, ctx, required_fn=required_fn)
    if err is not None:
        return None
    cost = realistic_cost(d.spread_pips)
    pip = _pip_size(symbol)
    grid_h = GRID_H_SHORT if fair_price_mode else GRID_H
    best = None
    for q in GRID_Q:
        for h in grid_h:
            if fair_price_mode:
                frame = evaluate_fair_price_trades(out, d.mid, cost, d.test_month, pip, q, h)
            else:
                frame = evaluate_trades(out, d.mid, cost, d.test_month, pip, q, h)
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
    ap.add_argument("--c-branch", type=float, default=0.7,
                    help="diversity bonus weight for branch-aware selection (default 0.7)")
    ap.add_argument("--p-recombine", type=float, default=0.25,
                    help="probability of cross-parent recombination vs single-parent propose (default 0.25)")
    ap.add_argument("--p-cross-branch", type=float, default=0.35,
                    help="probability of jumping to a different branch's template on propose (default 0.35)")
    ap.add_argument("--branch-depth-limit", type=int, default=3,
                    help="max consecutive expansions within the same branch before forcing a cross-branch jump (default 3)")
    ap.add_argument("--archive-threshold", type=float, default=-0.5,
                    help="save programs with validation score above this threshold to data/era_winners/ (default -0.5)")
    ap.add_argument("--fair-price", action="store_true",
                    help="fair-price mode: programs define estimate_fair(ctx) and we trade on deviations (h=1-20)")
    args = ap.parse_args()
    grid_h = GRID_H_SHORT if args.fair_price else GRID_H
    # For fair-price mode, score on all historical data (2018-2024) so the Bayesian
    # monthly-net posterior has ~84 months of statistical power.  Holdout stays 2025-26.
    if args.fair_price:
        sp = build_trade_splits(
            args.symbol, Path(args.tv_dir) / f"{args.symbol}_100tick_velocity.parquet",
            embargo=max(grid_h),
            train=("2018", "2019", "2020", "2021", "2022", "2023"),
            validation=("2018", "2019", "2020", "2021", "2022", "2023", "2024"),
            holdout=("2025", "2026"),
        )
    else:
        sp = build_trade_splits(args.symbol, Path(args.tv_dir) / f"{args.symbol}_100tick_velocity.parquet",
                                embargo=max(grid_h))
    if args.no_seeds:
        seed_programs = {"_root": FAIR_TRIVIAL_ROOT if args.fair_price else TRIVIAL_ROOT}
    else:
        seed_programs = None
    archive = WinnerArchive(args.symbol, threshold=args.archive_threshold)
    nodes = run_search(sp, args.symbol, budget=args.budget, select_policy=args.policy,
                       seed=args.seed, seed_programs=seed_programs,
                       p_recombine=args.p_recombine, p_cross_branch=args.p_cross_branch,
                       c_branch=args.c_branch, branch_depth_limit=args.branch_depth_limit,
                       archive=archive, fair_price_mode=args.fair_price)
    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=lambda n: n.score, reverse=True)
    # Deduplicate by payload so the same generated program doesn't dominate the top-5 display.
    seen_payloads: set[str] = set()
    unique_ranked = []
    for nd in ranked:
        if nd.payload not in seen_payloads:
            seen_payloads.add(nd.payload)
            unique_ranked.append(nd)
    mode_label = "fair-price" if args.fair_price else "cost-aware"
    lines = [f"# {mode_label} PUCT verdict — {args.symbol} (policy={args.policy}, "
             f"seeds={'no' if args.no_seeds else 'yes'}, budget={args.budget})\n"]
    for nd in unique_ranked[:5]:
        hv = holdout_verdict(nd.payload, sp["holdout"], args.symbol, fair_price_mode=args.fair_price)
        tag = "SEED" if nd.parent is None else "evolved"
        branch_tag = f"[{nd.branch}]" if nd.branch else ""
        if hv:
            lines.append(f"- [{tag}] {branch_tag} val={nd.score:+.3f} | holdout P={hv['p_positive']:.3f} "
                         f"raw={hv['raw_mean']:+.3f} (q{hv['q']} h{hv['h']} n={hv['n_trades']})")
            # Archive top-5 holdout results as well
            archive.save(nd.payload, nd.score, nd.mean, nd.se, nd.branch, nd.parent, hv)
        else:
            lines.append(f"- [{tag}] {branch_tag} val={nd.score:+.3f} | holdout: program error")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

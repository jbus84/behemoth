from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from scripts.era.llm import propose_program, recombine_program
from scripts.era.puct import Node, puct_search, select_thompson
from scripts.era_scalp.bayes_edge import edge_verdict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_aware_score import GRID_H, GRID_Q, CostAwarePerSymbolScorer
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era_scalp.load_splits import _pip_size, build_trade_splits
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.trade_harness import evaluate_trades

SYMBOL_DEFAULT = "EURUSD"
TRIVIAL_ROOT = "def signal(ctx):\n    return ctx.col('vel_pips_h1') * 0.0 + ctx.col('vel_pips_h1')\n"
FADE_RULES = (
    "You write `signal(ctx) -> np.ndarray`, one per-bar real value; sign = trade side, |value| ranks "
    "entries. ctx.col(name) gives causal columns; np available; no imports; never read future rows "
    "(a causality probe rejects it). Output ONE ```python block.\n"
)


def run_search(splits, symbol, budget, select_policy="thompson", seed=0,
               cache_dir="/tmp/era_eur_cache", p_recombine=0.3, seed_programs=None):
    scorer = CostAwarePerSymbolScorer(splits, symbol)
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)
    if seed_programs is None:
        seed_programs = FADE_SEED_PROGRAMS
    forest = []
    for src in seed_programs.values():
        v, mean, se, lg = scorer.score(src, "validation")
        forest.append(Node(payload=src, score=v, parent=None, logs=lg, mean=mean, se=se))
    all_nodes = list(forest)

    def expand(parent: Node) -> Node:
        if rng.random() < p_recombine and len(all_nodes) >= 2:
            cands = sorted(all_nodes, key=lambda n: n.score, reverse=True)
            child_src = recombine_program(cands[0].payload, cands[0].score, cands[1].payload,
                                          cands[1].score, cache_dir=cache_dir, rules=FADE_RULES)
        else:
            child_src = propose_program(parent.payload, parent.score, parent.logs,
                                        rng.choice(RESEARCH_IDEAS), cache_dir=cache_dir, rules=FADE_RULES)
        v, mean, se, lg = scorer.score(child_src, "validation")
        child = Node(payload=child_src, score=v, parent=parent, logs=lg, mean=mean, se=se)
        all_nodes.append(child)
        return child

    if select_policy == "thompson":
        select_fn = lambda ns, c: select_thompson(ns, nprng)
    else:
        select_fn = None  # default rank-based select
    return puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed, select_fn=select_fn)


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
    ap.add_argument("--policy", default="thompson", choices=["thompson", "rank"])
    ap.add_argument("--no-seeds", action="store_true", help="rediscovery control")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="/tmp/era_eur/verdict.md")
    args = ap.parse_args()
    sp = build_trade_splits(args.symbol, Path(args.tv_dir) / f"{args.symbol}_100tick_velocity.parquet",
                            embargo=max(GRID_H))
    seed_programs = {"_root": TRIVIAL_ROOT} if args.no_seeds else None
    nodes = run_search(sp, args.symbol, budget=args.budget, select_policy=args.policy,
                       seed=args.seed, seed_programs=seed_programs)
    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=lambda n: n.score, reverse=True)
    lines = [f"# Cost-aware PUCT verdict — {args.symbol} (policy={args.policy}, "
             f"seeds={'no' if args.no_seeds else 'yes'}, budget={args.budget})\n"]
    for nd in ranked[:5]:
        hv = holdout_verdict(nd.payload, sp["holdout"], args.symbol)
        tag = "SEED" if nd.parent is None else "evolved"
        if hv:
            lines.append(f"- [{tag}] val={nd.score:+.3f} | holdout P={hv['p_positive']:.3f} "
                         f"raw={hv['raw_mean']:+.3f} (q{hv['q']} h{hv['h']} n={hv['n_trades']})")
        else:
            lines.append(f"- [{tag}] val={nd.score:+.3f} | holdout: program error")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

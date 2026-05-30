from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from scripts.era.context import CrossSectionContext
from scripts.era.harness import entry_diagnostics, evaluate_residual
from scripts.era.llm import propose_program, recombine_program
from scripts.era.puct import Node, puct_search
from scripts.era.sandbox import run_program
from scripts.era.score_program import ProgramScorer, SplitData
from scripts.era.seeds import BASELINE_SEED_NAMES, RESEARCH_IDEAS, SEED_PROGRAMS
from scripts.era.select import bh_fdr, holdout_pvalue


def run_search(
    splits: dict[str, SplitData],
    thresholds,
    budget,
    writer=propose_program,
    ideas=None,
    seed: int = 0,
    cache_dir: str = "/tmp/era_cache",
    p_recombine: float = 0.3,
    seed_programs=None,
):
    ideas = ideas or RESEARCH_IDEAS
    seed_programs = seed_programs or SEED_PROGRAMS
    scorer = ProgramScorer(splits=splits, thresholds=thresholds)
    rng = random.Random(seed)
    # build forest: all seeds as independent roots with parent=None
    split_for_rank = "validation" if "validation" in splits else "train"
    forest = []
    for _name, src in seed_programs.items():
        s, lg = scorer.score(src, split_for_rank)
        nd = Node(payload=src, score=s, parent=None, logs=lg)
        forest.append(nd)

    all_nodes = list(forest)  # mutable list that expand can read

    def expand(parent: Node) -> Node:
        # with probability p_recombine, combine two strong parents
        if rng.random() < p_recombine and len(all_nodes) >= 2:
            # find two distinct high-scoring nodes
            distinct = {}
            for nd in all_nodes:
                key = id(nd.payload)
                if key not in distinct or nd.score > distinct[key].score:
                    distinct[key] = nd
            candidates = list(distinct.values())
            if len(candidates) >= 2:
                candidates.sort(key=lambda n: n.score, reverse=True)
                srcA, scoreA = candidates[0].payload, candidates[0].score
                srcB, scoreB = candidates[1].payload, candidates[1].score
                child_src = recombine_program(srcA, scoreA, srcB, scoreB, cache_dir=cache_dir)
            else:
                # fall back to mutation if not enough distinct programs
                idea = rng.choice(ideas)
                child_src = writer(
                    parent.payload, parent.score, parent.logs, idea, cache_dir=cache_dir
                )
        else:
            # mutate from parent
            idea = rng.choice(ideas)
            child_src = writer(parent.payload, parent.score, parent.logs, idea, cache_dir=cache_dir)

        s, lg = scorer.score(child_src, split_for_rank)
        child = Node(payload=child_src, score=s, parent=parent, logs=lg)
        all_nodes.append(child)  # update pool for next expand calls
        return child

    # PUCT selects and expands over the full forest
    nodes = puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed)
    return nodes


def select_seed_programs(no_baseline: bool = False) -> dict:
    if not no_baseline:
        return dict(SEED_PROGRAMS)
    return {k: v for k, v in SEED_PROGRAMS.items() if k not in BASELINE_SEED_NAMES}


def finalize_selection(holdout_nets: dict, q: float = 0.10) -> list[str]:
    """BH-FDR over explored programs using one-sided holdout p-values."""
    names = list(holdout_nets)
    pvals = np.array([holdout_pvalue(holdout_nets[n]["net"].to_numpy(float)) for n in names])
    keep = bh_fdr(pvals, q=q)
    return [n for n, k in zip(names, keep, strict=True) if k]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--bar-ticks", type=int, default=2000)
    ap.add_argument("--budget", type=int, default=60)
    ap.add_argument("--tom-dir", required=True)
    ap.add_argument("--velocity-dir", required=True)
    ap.add_argument("--horizon", type=int, default=3)
    ap.add_argument("--out", default="/tmp/era/report.md")
    ap.add_argument("--no-baseline-seeds", action="store_true",
                    help="drop the 4 canonical baselines (rediscovery tracer)")
    ap.add_argument("--holdout-top", type=int, default=5,
                    help="re-score top-N on holdout + BH-FDR")
    args = ap.parse_args()
    from scripts.era.load_splits import build_splits

    splits = build_splits(
        args.symbol,
        args.bar_ticks,
        Path(args.tom_dir),
        Path(args.velocity_dir),
        horizon=args.horizon,
    )
    seed_programs = select_seed_programs(no_baseline=args.no_baseline_seeds)
    nodes = run_search(splits, thresholds=[1.0, 1.5, 2.0, 2.5], budget=args.budget,
                       seed_programs=seed_programs)
    nodes.sort(key=lambda n: n.score, reverse=True)

    holdout = splits["holdout"]
    thresholds = [1.0, 1.5, 2.0, 2.5]
    top = nodes[: args.holdout_top]
    holdout_nets, diag_rows = {}, {}
    for i, nd in enumerate(top):
        ctx = CrossSectionContext(r=holdout.r, names=holdout.names, target=holdout.target,
                                  usd_sign=holdout.usd_sign, hour=holdout.hour)
        resid, err, _ = run_program(nd.payload, ctx)
        if err is not None:
            continue
        disp = ctx.dispersion()
        best = None
        for thr in thresholds:
            df = evaluate_residual(resid, holdout.usd_sign, holdout.y_fwd, holdout.cost,
                                   holdout.test_month, thr)
            if len(df) >= 5 and (best is None or len(df) < len(best[1])):
                best = (thr, df)
        if best is None:
            continue
        key = f"node{i}"
        holdout_nets[key] = best[1]
        diag_rows[key] = entry_diagnostics(resid, disp, holdout.usd_sign, holdout.y_fwd,
                                           holdout.cost, holdout.test_month, best[0])
    survivors = finalize_selection(holdout_nets, q=0.10) if holdout_nets else []

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(f"# ERA run — {args.symbol} {args.bar_ticks}tick (h{args.horizon})\n\n")
        f.write(f"nodes: {len(nodes)} | no_baseline_seeds={args.no_baseline_seeds}\n\n")
        f.write(f"## BH-FDR holdout survivors (q=0.10): {survivors or 'none'}\n\n")
        f.write("## Top by validation score (with holdout diagnostics)\n\n")
        for i, nd in enumerate(top):
            d = diag_rows.get(f"node{i}", {})
            f.write(f"- val_score={nd.score:.4f} holdout={d}\n```python\n{nd.payload}\n```\n")
    print(f"wrote {args.out}; survivors={survivors}")


if __name__ == "__main__":
    main()

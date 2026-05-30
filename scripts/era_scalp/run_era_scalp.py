from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from scripts.era.llm import propose_program, recombine_program
from scripts.era.puct import Node, puct_search
from scripts.era.select import bh_fdr, holdout_pvalue
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.harness import entry_diagnostics, evaluate_signal
from scripts.era_scalp.prompt import SCALP_RULES
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.score_program import ScalpScorer
from scripts.era_scalp.seeds import BASELINE_SEED_NAMES, RESEARCH_IDEAS, SEED_PROGRAMS

THRESHOLDS = [0.5, 1.0, 1.5, 2.0]


def select_seed_programs(no_baseline: bool = False) -> dict:
    if not no_baseline:
        return dict(SEED_PROGRAMS)
    return {k: v for k, v in SEED_PROGRAMS.items() if k not in BASELINE_SEED_NAMES}


def summarize_rejections(nodes) -> dict:
    """Count how many explored programs were rejected (scored -1e6) and why,
    so silent losses (timeouts, causality, errors) are visible in the report."""
    rej = {"total": len(nodes), "rejected": 0, "timeout": 0,
           "causality": 0, "static_or_exec": 0, "other": 0}
    for nd in nodes:
        if nd.score > -1e6 + 1.0:
            continue
        rej["rejected"] += 1
        lg = (nd.logs or "").lower()
        if "timeout" in lg:
            rej["timeout"] += 1
        elif "causality_probe" in lg:
            rej["causality"] += 1
        elif "static_check" in lg or "exec" in lg:
            rej["static_or_exec"] += 1
        else:
            rej["other"] += 1
    return rej


def finalize_selection(holdout_nets: dict, q: float = 0.10) -> list[str]:
    names = list(holdout_nets)
    pvals = np.array([holdout_pvalue(holdout_nets[n]["net"].to_numpy(float)) for n in names])
    keep = bh_fdr(pvals, q=q)
    return [n for n, k in zip(names, keep, strict=True) if k]


def run_search(
    splits,
    thresholds,
    budget,
    writer=propose_program,
    ideas=None,
    seed: int = 0,
    cache_dir: str = "/tmp/era_scalp_cache",
    p_recombine: float = 0.3,
    seed_programs=None,
):
    ideas = ideas or RESEARCH_IDEAS
    seed_programs = seed_programs or SEED_PROGRAMS
    scorer = ScalpScorer(splits=splits, thresholds=thresholds)
    rng = random.Random(seed)
    split_for_rank = "validation" if "validation" in splits else "train"
    forest = []
    for _name, src in seed_programs.items():
        s, lg = scorer.score(src, split_for_rank)
        forest.append(Node(payload=src, score=s, parent=None, logs=lg))
    all_nodes = list(forest)

    def expand(parent: Node) -> Node:
        if rng.random() < p_recombine and len(all_nodes) >= 2:
            distinct = {}
            for nd in all_nodes:
                key = id(nd.payload)
                if key not in distinct or nd.score > distinct[key].score:
                    distinct[key] = nd
            cands = sorted(distinct.values(), key=lambda n: n.score, reverse=True)
            if len(cands) >= 2:
                child_src = recombine_program(
                    cands[0].payload,
                    cands[0].score,
                    cands[1].payload,
                    cands[1].score,
                    cache_dir=cache_dir,
                    rules=SCALP_RULES,
                )
            else:
                idea = rng.choice(ideas)
                child_src = writer(
                    parent.payload,
                    parent.score,
                    parent.logs,
                    idea,
                    cache_dir=cache_dir,
                    rules=SCALP_RULES,
                )
        else:
            idea = rng.choice(ideas)
            child_src = writer(
                parent.payload,
                parent.score,
                parent.logs,
                idea,
                cache_dir=cache_dir,
                rules=SCALP_RULES,
            )
        s, lg = scorer.score(child_src, split_for_rank)
        child = Node(payload=child_src, score=s, parent=parent, logs=lg)
        all_nodes.append(child)
        return child

    return puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--parquet", required=True, help="path to <SYMBOL>_100tick_velocity.parquet")
    ap.add_argument("--horizon", type=int, default=1)
    ap.add_argument("--budget", type=int, default=60)
    ap.add_argument("--no-baseline-seeds", action="store_true")
    ap.add_argument("--holdout-top", type=int, default=5)
    ap.add_argument("--score-max-bars", type=int, default=50000,
                    help="cap the validation ranking split to its most-recent N bars "
                         "(keeps heavy programs under the 10s timeout; 0 = no cap)")
    ap.add_argument("--out", default="/tmp/era_scalp/report.md")
    args = ap.parse_args()
    from scripts.era_scalp.load_splits import build_splits, cap_recent

    splits = build_splits(args.symbol, Path(args.parquet), horizon=args.horizon)
    # Cap ONLY the validation ranking split for the discovery loop; holdout stays full.
    cap = args.score_max_bars or None
    splits["validation"] = cap_recent(splits["validation"], cap)
    seed_programs = select_seed_programs(no_baseline=args.no_baseline_seeds)
    nodes = run_search(
        splits, thresholds=THRESHOLDS, budget=args.budget, seed_programs=seed_programs
    )
    nodes.sort(key=lambda n: n.score, reverse=True)

    hold = splits["holdout"]
    top = nodes[: args.holdout_top]
    holdout_nets, diag_rows = {}, {}
    for i, nd in enumerate(top):
        ctx = FeatureContext(X=hold.X, names=hold.names, hour=hold.hour)
        sig, err, _ = run_program(nd.payload, ctx)
        if err is not None:
            continue
        best = None
        for thr in THRESHOLDS:
            df = evaluate_signal(sig, hold.y_fwd, hold.cost, hold.test_month, thr)
            if len(df) >= 5 and (best is None or len(df) < len(best[1])):
                best = (thr, df)
        if best is None:
            continue
        key = f"node{i}"
        holdout_nets[key] = best[1]
        diag_rows[key] = entry_diagnostics(
            sig, hold.y_fwd, hold.cost, hold.test_month, best[0]
        )
    survivors = finalize_selection(holdout_nets, q=0.10) if holdout_nets else []
    health = summarize_rejections(nodes)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(f"# ERA-scalp run — {args.symbol} 100tick (h{args.horizon})\n\n")
        f.write(f"nodes: {len(nodes)} | no_baseline_seeds={args.no_baseline_seeds} "
                f"| score_max_bars={cap}\n\n")
        f.write(f"## Search health: {health}\n\n")
        f.write(f"## BH-FDR holdout survivors (q=0.10): {survivors or 'none'}\n\n")
        f.write("## Top by validation score (with holdout diagnostics)\n\n")
        for i, nd in enumerate(top):
            d = diag_rows.get(f"node{i}", {})
            f.write(f"- val_score={nd.score:.4f} holdout={d}\n```python\n{nd.payload}\n```\n")
    print(f"wrote {args.out}; survivors={survivors}")


if __name__ == "__main__":
    main()

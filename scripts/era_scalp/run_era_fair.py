from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from scripts.era.llm import propose_program, recombine_program
from scripts.era.puct import Node, puct_search
from scripts.era.select import bh_fdr
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fair_harness import (
    W_GRID,
    fair_diagnostics,
    forward_dev,
    ic_pvalue,
    info_coefficient,
)
from scripts.era_scalp.fair_prompt import FAIR_RULES
from scripts.era_scalp.fair_score import _PIP, FairScorer
from scripts.era_scalp.fair_seeds import BASELINE_SEED_NAMES, FAIR_SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era_scalp.sandbox import run_program


def select_seed_programs(no_baseline: bool = False) -> dict:
    if not no_baseline:
        return dict(FAIR_SEED_PROGRAMS)
    return {k: v for k, v in FAIR_SEED_PROGRAMS.items() if k not in BASELINE_SEED_NAMES}


def finalize_selection(cand_ic_n: dict, q: float = 0.10) -> list[str]:
    """cand_ic_n: name -> (holdout_ic, n_eff). BH-FDR over two-sided IC p-values."""
    names = list(cand_ic_n)
    pvals = np.array([ic_pvalue(cand_ic_n[n][0], cand_ic_n[n][1]) for n in names])
    keep = bh_fdr(pvals, q=q)
    return [n for n, k in zip(names, keep, strict=True) if k]


def summarize_rejections(nodes) -> dict:
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


def run_search(splits, symbol, budget, writer=propose_program, ideas=None, seed: int = 0,
               cache_dir: str = "/tmp/era_fair_cache", p_recombine: float = 0.3,
               seed_programs=None):
    ideas = ideas or RESEARCH_IDEAS
    seed_programs = seed_programs or FAIR_SEED_PROGRAMS
    scorer = FairScorer(splits=splits, symbol=symbol)
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
                child_src = recombine_program(cands[0].payload, cands[0].score,
                                              cands[1].payload, cands[1].score,
                                              cache_dir=cache_dir, rules=FAIR_RULES)
            else:
                child_src = writer(parent.payload, parent.score, parent.logs,
                                   rng.choice(ideas), cache_dir=cache_dir, rules=FAIR_RULES)
        else:
            child_src = writer(parent.payload, parent.score, parent.logs,
                               rng.choice(ideas), cache_dir=cache_dir, rules=FAIR_RULES)
        s, lg = scorer.score(child_src, split_for_rank)
        child = Node(payload=child_src, score=s, parent=parent, logs=lg)
        all_nodes.append(child)
        return child

    return puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed)


def _holdout_best(src, d, symbol):
    ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
    pred, err, _ = run_program(src, ctx, required_fn="fair")
    if err is not None:
        return None
    pip = _PIP[str(symbol).upper()]
    best = None
    for W in W_GRID:
        ic, n = info_coefficient(pred, forward_dev(d.mid, pip, W))
        if np.isfinite(ic) and (best is None or abs(ic) > abs(best[0])):
            best = (ic, n, W)
    if best is None:
        return None
    ic, n, W = best
    return ic, n, W, fair_diagnostics(pred, d.mid, pip, d.test_month, W)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--budget", type=int, default=60)
    ap.add_argument("--no-baseline-seeds", action="store_true")
    ap.add_argument("--holdout-top", type=int, default=8)
    ap.add_argument("--score-max-bars", type=int, default=50000)
    ap.add_argument("--out", default="/tmp/era_fair/report.md")
    args = ap.parse_args()
    from scripts.era_scalp.load_splits import build_fair_splits

    splits = build_fair_splits(args.symbol, Path(args.parquet), embargo=max(W_GRID))
    cap = args.score_max_bars or None
    if cap and splits["validation"].X.shape[0] > cap:
        v = splits["validation"]
        sl = slice(v.X.shape[0] - cap, None)
        splits["validation"] = type(v)(X=v.X[sl], names=v.names,
                                        hour=None if v.hour is None else v.hour[sl],
                                        mid=v.mid[sl], test_month=v.test_month[sl])
    seed_programs = select_seed_programs(no_baseline=args.no_baseline_seeds)
    nodes = run_search(splits, symbol=args.symbol, budget=args.budget,
                       seed_programs=seed_programs)
    nodes.sort(key=lambda n: n.score, reverse=True)

    hold = splits["holdout"]
    top = nodes[: args.holdout_top]
    cand, diag_rows = {}, {}
    for i, nd in enumerate(top):
        res = _holdout_best(nd.payload, hold, args.symbol)
        if res is None:
            continue
        ic, n, W, diag = res
        cand[f"node{i}"] = (ic, n)
        diag_rows[f"node{i}"] = {"W": W, **diag}
    survivors = finalize_selection(cand, q=0.10) if cand else []
    health = summarize_rejections(nodes)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(f"# ERA-fair run - {args.symbol} 100tick\n\n")
        f.write(f"nodes: {len(nodes)} | no_baseline_seeds={args.no_baseline_seeds} "
                f"| score_max_bars={cap}\n\n")
        f.write(f"## Search health: {health}\n\n")
        f.write(f"## BH-FDR holdout IC survivors (q=0.10): {survivors or 'none'}\n\n")
        f.write("## Top by validation node-score (with holdout IC diagnostics)\n\n")
        for i, nd in enumerate(top):
            dd = diag_rows.get(f"node{i}", {})
            f.write(f"- node_score={nd.score:.3f} holdout={dd}\n```python\n{nd.payload}\n```\n")
    print(f"wrote {args.out}; survivors={survivors}")


if __name__ == "__main__":
    main()

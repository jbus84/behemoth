from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from scripts.era.llm import propose_program, recombine_program
from scripts.era.puct import Node, puct_search
from scripts.era.select import bh_fdr, holdout_pvalue
from scripts.era_scalp.bracket_harness import deploy_diagnostics, evaluate_deploy
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.load_splits import build_range_splits, cap_recent_range
from scripts.era_scalp.range_prompt import RANGE_RULES
from scripts.era_scalp.range_score import _DELTAS, _MAXHOLDS, _PIP, _QS, _STOPS, RangeScorer
from scripts.era_scalp.range_seeds import BASELINE_SEED_NAMES, DEPLOY_SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era_scalp.sandbox import run_program


def select_seed_programs(no_baseline: bool = False) -> dict:
    if not no_baseline:
        return dict(DEPLOY_SEED_PROGRAMS)
    return {k: v for k, v in DEPLOY_SEED_PROGRAMS.items() if k not in BASELINE_SEED_NAMES}


def finalize_selection(holdout_nets: dict, q: float = 0.10) -> list[str]:
    names = list(holdout_nets)
    pvals = np.array([holdout_pvalue(holdout_nets[n]["net"].to_numpy(float)) for n in names])
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
               cache_dir: str = "/tmp/era_range_cache", p_recombine: float = 0.3,
               seed_programs=None):
    ideas = ideas or RESEARCH_IDEAS
    seed_programs = seed_programs or DEPLOY_SEED_PROGRAMS
    scorer = RangeScorer(splits=splits, symbol=symbol)
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
                                              cache_dir=cache_dir, rules=RANGE_RULES)
            else:
                child_src = writer(parent.payload, parent.score, parent.logs,
                                   rng.choice(ideas), cache_dir=cache_dir, rules=RANGE_RULES)
        else:
            child_src = writer(parent.payload, parent.score, parent.logs,
                               rng.choice(ideas), cache_dir=cache_dir, rules=RANGE_RULES)
        s, lg = scorer.score(child_src, split_for_rank)
        child = Node(payload=child_src, score=s, parent=parent, logs=lg)
        all_nodes.append(child)
        return child

    return puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed)


def _best_holdout(src, d, symbol, commission_pips):
    ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
    sig, err, _ = run_program(src, ctx, required_fn="deploy")
    if err is not None:
        return None, {}
    pip = _PIP[str(symbol).upper()]
    best = None
    best_params = None
    for q in _QS:
        for delta in _DELTAS:
            for stop in _STOPS:
                for kbars in _MAXHOLDS:
                    df = evaluate_deploy(
                        deploy_score=sig, close=d.close_bid, high=d.high_bid, low=d.low_bid,
                        spread=d.spread, cost=d.cost, test_month=d.test_month, q=q,
                        delta_pips=delta, stop_pips=stop, max_hold=kbars, pip=pip,
                        commission_pips=commission_pips)
                    if len(df) >= 20 and (best is None or len(df) < len(best)):
                        best, best_params = df, (q, delta, stop, kbars)
    if best is None:
        return None, {}
    q, delta, stop, kbars = best_params
    diag = deploy_diagnostics(
        deploy_score=sig, close=d.close_bid, high=d.high_bid, low=d.low_bid,
        spread=d.spread, cost=d.cost, test_month=d.test_month, q=q, delta_pips=delta,
        stop_pips=stop, max_hold=kbars, pip=pip, commission_pips=commission_pips)
    return best, diag


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--max-hold", type=int, default=10)
    ap.add_argument("--budget", type=int, default=60)
    ap.add_argument("--no-baseline-seeds", action="store_true")
    ap.add_argument("--holdout-top", type=int, default=5)
    ap.add_argument("--score-max-bars", type=int, default=50000)
    ap.add_argument("--commission-pips", type=float, default=0.07)
    ap.add_argument("--out", default="/tmp/era_range/report.md")
    args = ap.parse_args()
    splits = build_range_splits(args.symbol, Path(args.parquet), max_hold=args.max_hold)
    cap = args.score_max_bars or None
    if cap and splits["validation"].X.shape[0] > cap:
        splits["validation"] = cap_recent_range(splits["validation"], cap)
    seed_programs = select_seed_programs(no_baseline=args.no_baseline_seeds)
    nodes = run_search(splits, symbol=args.symbol, budget=args.budget,
                       seed_programs=seed_programs)
    nodes.sort(key=lambda n: n.score, reverse=True)

    hold = splits["holdout"]
    top = nodes[: args.holdout_top]
    holdout_nets, diag_rows = {}, {}
    for i, nd in enumerate(top):
        df, diag = _best_holdout(nd.payload, hold, args.symbol, args.commission_pips)
        if df is None:
            continue
        holdout_nets[f"node{i}"] = df
        diag_rows[f"node{i}"] = diag
    survivors = finalize_selection(holdout_nets, q=0.10) if holdout_nets else []
    health = summarize_rejections(nodes)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(f"# ERA-range run - {args.symbol} 100tick (max_hold={args.max_hold})\n\n")
        f.write(f"nodes: {len(nodes)} | no_baseline_seeds={args.no_baseline_seeds} "
                f"| score_max_bars={cap}\n\n")
        f.write(f"## Search health: {health}\n\n")
        f.write(f"## BH-FDR holdout survivors (q=0.10): {survivors or 'none'}\n\n")
        f.write("## Top by validation score (with holdout diagnostics)\n\n")
        for i, nd in enumerate(top):
            dd = diag_rows.get(f"node{i}", {})
            f.write(f"- val_score={nd.score:.4f} holdout={dd}\n```python\n{nd.payload}\n```\n")
    print(f"wrote {args.out}; survivors={survivors}")


if __name__ == "__main__":
    main()

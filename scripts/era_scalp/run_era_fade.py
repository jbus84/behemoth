from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.era.llm import propose_program, recombine_program
from scripts.era.puct import Node, puct_search
from scripts.era.select import bh_fdr, holdout_pvalue
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fade_prompt import FADE_RULES
from scripts.era_scalp.fade_seeds import BASELINE_SEED_NAMES, FADE_SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.trade_harness import evaluate_trades, per_symbol_net
from scripts.era_scalp.trade_score import GRID_H, GRID_Q, PooledTradeScorer

SYMBOLS = ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDJPY"]


def select_seed_programs(no_baseline: bool = False) -> dict:
    if not no_baseline:
        return dict(FADE_SEED_PROGRAMS)
    return {k: v for k, v in FADE_SEED_PROGRAMS.items() if k not in BASELINE_SEED_NAMES}


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


def run_search(splits_by_symbol, symbols, budget, writer=propose_program, ideas=None,
               seed: int = 0, cache_dir: str = "/tmp/era_fade_cache", p_recombine: float = 0.3,
               seed_programs=None, aggregate: str = "robust"):
    ideas = ideas or RESEARCH_IDEAS
    seed_programs = seed_programs or FADE_SEED_PROGRAMS
    scorer = PooledTradeScorer(splits_by_symbol, symbols=symbols, aggregate=aggregate)
    rng = random.Random(seed)
    forest = []
    for _name, src in seed_programs.items():
        s, lg = scorer.score(src, "validation")
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
                                              cache_dir=cache_dir, rules=FADE_RULES)
            else:
                child_src = writer(parent.payload, parent.score, parent.logs,
                                   rng.choice(ideas), cache_dir=cache_dir, rules=FADE_RULES)
        else:
            child_src = writer(parent.payload, parent.score, parent.logs,
                               rng.choice(ideas), cache_dir=cache_dir, rules=FADE_RULES)
        s, lg = scorer.score(child_src, "validation")
        child = Node(payload=child_src, score=s, parent=parent, logs=lg)
        all_nodes.append(child)
        return child

    return puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed)


def _pooled_holdout(src, splits_by_symbol, symbols):
    sigs, mids, costs, tms, pips = {}, {}, {}, {}, {}
    for sym in symbols:
        d = splits_by_symbol[sym]["holdout"]
        ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
        sig, err, _ = run_program(src, ctx, required_fn="signal")
        if err is not None:
            return None
        sigs[sym] = sig
        mids[sym] = d.mid
        costs[sym] = d.cost
        tms[sym] = d.test_month
        pips[sym] = _pip_size_local(sym)
    best = None
    for q in GRID_Q:
        for h in GRID_H:
            frames = [evaluate_trades(sigs[s], mids[s], costs[s], tms[s], pips[s], q, h)
                      for s in symbols]
            nz = [f for f in frames if len(f)]
            pooled = pd.concat(nz, ignore_index=True) if nz else pd.DataFrame(
                {"net": np.array([]), "test_month": np.array([])})
            if len(pooled) >= 50 and (best is None or len(pooled) < len(best[0])):
                best = (pooled, (q, h))
    if best is None:
        return None
    pooled, (q, h) = best
    psn = per_symbol_net(sigs, mids, costs, tms, pips, q, h)
    return pooled, psn, (q, h)


def _pip_size_local(sym):
    from scripts.era_scalp.load_splits import _pip_size
    return _pip_size(sym)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--budget", type=int, default=60)
    ap.add_argument("--no-baseline-seeds", action="store_true")
    ap.add_argument("--holdout-top", type=int, default=8)
    ap.add_argument("--score-max-bars", type=int, default=50000)
    ap.add_argument("--out", default="/tmp/era_fade/report.md")
    args = ap.parse_args()
    from scripts.era_scalp.load_splits import build_trade_splits

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    cap = args.score_max_bars or None
    by = {}
    for sym in symbols:
        sp = build_trade_splits(sym, Path(args.tv_dir) / f"{sym}_100tick_velocity.parquet",
                                embargo=max(GRID_H))
        if cap and sp["validation"].X.shape[0] > cap:
            v = sp["validation"]
            sl = slice(v.X.shape[0] - cap, None)
            sp["validation"] = type(v)(X=v.X[sl], names=v.names,
                                       hour=None if v.hour is None else v.hour[sl],
                                       mid=v.mid[sl], cost=v.cost[sl], test_month=v.test_month[sl])
        by[sym] = sp

    seed_programs = select_seed_programs(no_baseline=args.no_baseline_seeds)
    nodes = run_search(by, symbols=symbols, budget=args.budget, seed_programs=seed_programs)
    nodes.sort(key=lambda n: n.score, reverse=True)

    top = nodes[: args.holdout_top]
    holdout_nets, diag_rows = {}, {}
    for i, nd in enumerate(top):
        res = _pooled_holdout(nd.payload, by, symbols)
        if res is None:
            continue
        pooled, psn, (q, h) = res
        holdout_nets[f"node{i}"] = pooled
        diag_rows[f"node{i}"] = {"q": q, "h": h, "n": int(len(pooled)),
                                 "pooled_mean_net": float(pooled["net"].mean()),
                                 "per_symbol": psn}
    survivors = finalize_selection(holdout_nets, q=0.10) if holdout_nets else []
    health = summarize_rejections(nodes)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(f"# ERA-fade run - {symbols} 100tick (pooled)\n\n")
        f.write(f"nodes: {len(nodes)} | no_baseline_seeds={args.no_baseline_seeds} "
                f"| score_max_bars={cap}\n\n")
        f.write(f"## Search health: {health}\n\n")
        f.write(f"## BH-FDR pooled-holdout survivors (q=0.10): {survivors or 'none'}\n\n")
        f.write("## Top by pooled validation score (holdout pooled + PER-SYMBOL breakdown)\n\n")
        for i, nd in enumerate(top):
            dd = diag_rows.get(f"node{i}", {})
            f.write(f"- val_score={nd.score:.3f} holdout={dd}\n```python\n{nd.payload}\n```\n")
    print(f"wrote {args.out}; survivors={survivors}")


if __name__ == "__main__":
    main()

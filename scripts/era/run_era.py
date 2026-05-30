from __future__ import annotations

import argparse
import random
from pathlib import Path

from scripts.era.llm import propose_program, recombine_program
from scripts.era.puct import Node, puct_search
from scripts.era.score_program import ProgramScorer, SplitData
from scripts.era.seeds import RESEARCH_IDEAS, SEED_PROGRAMS


def run_search(
    splits: dict[str, SplitData],
    thresholds,
    budget,
    writer=propose_program,
    ideas=None,
    seed: int = 0,
    cache_dir: str = "/tmp/era_cache",
    p_recombine: float = 0.3,
):
    ideas = ideas or RESEARCH_IDEAS
    scorer = ProgramScorer(splits=splits, thresholds=thresholds)
    rng = random.Random(seed)
    # build forest: all seeds as independent roots with parent=None
    split_for_rank = "validation" if "validation" in splits else "train"
    forest = []
    for _name, src in SEED_PROGRAMS.items():
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--bar-ticks", type=int, default=2000)
    ap.add_argument("--budget", type=int, default=60)
    ap.add_argument("--tom-dir", required=True)
    ap.add_argument("--velocity-dir", required=True)
    ap.add_argument("--horizon", type=int, default=3)
    ap.add_argument("--out", default="/tmp/era/report.md")
    args = ap.parse_args()
    from scripts.era.load_splits import build_splits

    splits = build_splits(
        args.symbol,
        args.bar_ticks,
        Path(args.tom_dir),
        Path(args.velocity_dir),
        horizon=args.horizon,
    )
    nodes = run_search(splits, thresholds=[1.0, 1.5, 2.0, 2.5], budget=args.budget)
    nodes.sort(key=lambda n: n.score, reverse=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(f"# ERA SP1 run — {args.symbol} {args.bar_ticks}tick\n\n")
        f.write(f"nodes: {len(nodes)}\n\n## Top 10 by validation score\n\n")
        for nd in nodes[:10]:
            f.write(f"- score={nd.score:.4f}\n```python\n{nd.payload}\n```\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

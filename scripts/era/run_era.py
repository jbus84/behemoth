from __future__ import annotations
import argparse, random
from pathlib import Path
import numpy as np
from scripts.era.score_program import ProgramScorer, SplitData
from scripts.era.puct import Node, puct_search
from scripts.era.seeds import SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era.llm import propose_program

def run_search(splits: dict[str, SplitData], thresholds, budget, writer=propose_program,
               ideas=None, seed: int = 0, cache_dir: str = "/tmp/era_cache"):
    ideas = ideas or RESEARCH_IDEAS
    scorer = ProgramScorer(splits=splits, thresholds=thresholds)
    rng = random.Random(seed)
    # seed the tree with the best baseline as root; others as initial children
    root_src = SEED_PROGRAMS["loo_z"]
    rs, rlogs = scorer.score(root_src, "validation" if "validation" in splits else "train")
    root = Node(payload=root_src, score=rs, parent=None, logs=rlogs)
    nodes = [root]
    for name, src in SEED_PROGRAMS.items():
        if name == "loo_z":
            continue
        s, lg = scorer.score(src, "validation" if "validation" in splits else "train")
        ch = Node(payload=src, score=s, parent=root, logs=lg)
        root.children.append(ch); nodes.append(ch)

    split_for_rank = "validation" if "validation" in splits else "train"
    def expand(parent: Node) -> Node:
        idea = rng.choice(ideas)
        child_src = writer(parent.payload, parent.score, parent.logs, idea, cache_dir=cache_dir)
        s, lg = scorer.score(child_src, split_for_rank)
        return Node(payload=child_src, score=s, parent=parent, logs=lg)

    # continue PUCT from the seeded forest
    extra = puct_search(root, expand, budget=budget, c_puct=1.0, seed=seed)
    # puct_search starts from root only; merge the pre-seeded children list
    seen = {id(n) for n in extra}
    for n in nodes:
        if id(n) not in seen:
            extra.append(n)
    return extra

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
    splits = build_splits(args.symbol, args.bar_ticks, Path(args.tom_dir),
                          Path(args.velocity_dir), horizon=args.horizon)
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

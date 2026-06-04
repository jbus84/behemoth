#!/usr/bin/env python3
"""Run N independent ERA-PUCT trees in parallel and aggregate results.

This covers more search space in the same wall-clock time as one large tree,
with less risk of branch capture by any single stochastic LLM trajectory.

Usage:
    uv run python -m scripts.era_scalp.run_era_parallel \
        --symbol EURUSD --budget 40 --trees 5 --out /tmp/era_eur/parallel_verdict.md
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def _run_tree(args: dict, tree_seed: int, out_dir: Path) -> dict | None:
    """Launch a single ERA tree as a subprocess."""
    out_file = out_dir / f"verdict_tree_{tree_seed}.md"
    cmd = [
        sys.executable, "-m", "scripts.era_scalp.run_era_eur",
        "--symbol", args["symbol"],
        "--tv-dir", args["tv_dir"],
        "--budget", str(args["budget"]),
        "--policy", args["policy"],
        "--seed", str(tree_seed),
        "--c-branch", str(args["c_branch"]),
        "--p-recombine", str(args["p_recombine"]),
        "--p-cross-branch", str(args["p_cross_branch"]),
        "--branch-depth-limit", str(args["branch_depth_limit"]),
        "--archive-threshold", str(args["archive_threshold"]),
        "--out", str(out_file),
    ]
    if args.get("no_seeds"):
        cmd.append("--no-seeds")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            print(f"[tree {tree_seed}] FAILED: {result.stderr[:500]}")
            return None
        # Parse the verdict markdown for top entries
        lines = out_file.read_text().splitlines()
        entries = []
        for line in lines:
            if line.startswith("- ["):
                entries.append(line)
        return {"seed": tree_seed, "entries": entries, "raw": lines}
    except subprocess.TimeoutExpired:
        print(f"[tree {tree_seed}] TIMEOUT after 3600s")
        return None
    except Exception as e:
        print(f"[tree {tree_seed}] ERROR: {e}")
        return None


def aggregate(trees: list[dict | None]) -> str:
    """Aggregate results from all trees into a single verdict."""
    # Collect all entries across trees
    all_entries: list[tuple[int, str]] = []
    for tree in trees:
        if tree is None:
            continue
        for entry in tree["entries"]:
            all_entries.append((tree["seed"], entry))

    # Parse scores from entries
    scored: list[tuple[float, int, str]] = []
    for seed, entry in all_entries:
        # Extract val= score
        try:
            score_str = entry.split("val=")[1].split(" |")[0].strip()
            score = float(score_str)
            scored.append((score, seed, entry))
        except (IndexError, ValueError):
            continue

    scored.sort(reverse=True)

    lines = ["# Parallel ERA-PUCT Verdict — Multi-Tree Aggregate\n"]
    lines.append(f"Trees: {len([t for t in trees if t is not None])} | Budget per tree: see individual files\n")
    lines.append("## Top 10 programs across all trees\n")
    seen_payloads: set[str] = set()
    rank = 0
    for _score, seed, entry in scored:
        # Simple dedup by exact line content (payload not available here)
        if entry in seen_payloads:
            continue
        seen_payloads.add(entry)
        rank += 1
        lines.append(f"{rank}. [tree={seed}] {entry}")
        if rank >= 10:
            break

    # Branch coverage summary
    branch_counts: dict[str, int] = {}
    for tree in trees:
        if tree is None:
            continue
        for entry in tree["entries"]:
            if "[" in entry and "]" in entry:
                try:
                    branch = entry.split("[")[2].split("]")[0]
                    branch_counts[branch] = branch_counts.get(branch, 0) + 1
                except IndexError:
                    continue

    lines.append("\n## Branch coverage across all trees\n")
    for branch, count in sorted(branch_counts.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {branch}: {count} entries")

    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run N independent ERA-PUCT trees in parallel")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--budget", type=int, default=40, help="budget per tree")
    ap.add_argument("--trees", type=int, default=5, help="number of parallel trees")
    ap.add_argument("--policy", default="diversity", choices=["thompson", "rank", "diversity"])
    ap.add_argument("--no-seeds", action="store_true")
    ap.add_argument("--c-branch", type=float, default=0.7)
    ap.add_argument("--p-recombine", type=float, default=0.25)
    ap.add_argument("--p-cross-branch", type=float, default=0.35)
    ap.add_argument("--branch-depth-limit", type=int, default=3)
    ap.add_argument("--archive-threshold", type=float, default=-0.5)
    ap.add_argument("--out", default="/tmp/era_eur/parallel_verdict.md")
    args = ap.parse_args()

    out_dir = Path(args.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    arg_dict = {
        "symbol": args.symbol,
        "tv_dir": args.tv_dir,
        "budget": args.budget,
        "policy": args.policy,
        "no_seeds": args.no_seeds,
        "c_branch": args.c_branch,
        "p_recombine": args.p_recombine,
        "p_cross_branch": args.p_cross_branch,
        "branch_depth_limit": args.branch_depth_limit,
        "archive_threshold": args.archive_threshold,
    }

    print(f"[parallel] launching {args.trees} trees, budget={args.budget} each")
    with ThreadPoolExecutor(max_workers=args.trees) as ex:
        futures = {ex.submit(_run_tree, arg_dict, seed, out_dir): seed
                   for seed in range(args.trees)}
        results = []
        for fut in as_completed(futures):
            seed = futures[fut]
            result = fut.result()
            results.append(result)
            status = "OK" if result else "FAIL"
            print(f"[parallel] tree {seed} {status}")

    report = aggregate(results)
    Path(args.out).write_text(report + "\n")
    print(f"wrote {args.out}")
    print(report)


if __name__ == "__main__":
    main()

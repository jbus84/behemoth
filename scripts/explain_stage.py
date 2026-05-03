#!/usr/bin/env python3
"""Generate an LLM-readable stage capsule from the executable process registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.behemoth.ops.process_graph import (  # noqa: E402
    build_stage_graph,
    render_stage_capsule_markdown,
)
from src.behemoth.ops.process_registry import load_stage_registry  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage_id", help="Stage ID, for example stage14")
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("configs/process/stages.yaml"),
        help="Executable process registry YAML.",
    )
    parser.add_argument(
        "--graphify-json",
        type=Path,
        default=None,
        help="Optional Graphify graph.json to project onto the declared stage scope.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional markdown output path. Prints to stdout when omitted.",
    )
    parser.add_argument(
        "--graph-out",
        type=Path,
        default=None,
        help="Optional scoped graph JSON output path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry = load_stage_registry(args.registry)
    stage = registry.require_stage(args.stage_id)
    graph = build_stage_graph(stage, repo_root=REPO_ROOT, graphify_json=args.graphify_json)
    markdown = render_stage_capsule_markdown(stage, graph)

    wrote: list[str] = []
    if args.graph_out:
        args.graph_out.parent.mkdir(parents=True, exist_ok=True)
        args.graph_out.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
        wrote.append(str(args.graph_out))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown, encoding="utf-8")
        wrote.append(str(args.out))
    else:
        print(markdown)

    if wrote:
        print(f"wrote {', '.join(wrote)}")


if __name__ == "__main__":
    main()

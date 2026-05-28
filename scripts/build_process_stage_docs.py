#!/usr/bin/env python3
"""Build scoped process graphs and generated LLM capsules for every registry stage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.behemoth.governance.stage_contracts import render_stage_io_contract  # noqa: E402
from src.behemoth.ops.process_graph import (  # noqa: E402
    build_stage_graph,
    render_stage_capsule_markdown,
)
from src.behemoth.ops.process_registry import load_stage_registry  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
        help="Optional Graphify graph.json to project onto each declared stage scope.",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("docs/generated/process"),
        help="Output directory for generated stage capsules.",
    )
    parser.add_argument(
        "--graph-dir",
        type=Path,
        default=Path("data/analysis/process_graph"),
        help="Output directory for scoped graph JSON and scope manifests.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry = load_stage_registry(args.registry)
    args.docs_dir.mkdir(parents=True, exist_ok=True)
    args.graph_dir.mkdir(parents=True, exist_ok=True)

    index_lines = [
        "# Process Stage Capsules",
        "",
        "Generated from `configs/process/stages.yaml`. Do not edit these files by hand.",
        "",
    ]
    for stage_id in sorted(registry.stages):
        stage = registry.require_stage(stage_id)
        graph = build_stage_graph(stage, repo_root=REPO_ROOT, graphify_json=args.graphify_json)
        md = render_stage_capsule_markdown(stage, graph)
        contract_md = render_stage_io_contract(stage_id)
        if contract_md:
            md += "\n\n" + contract_md
        (args.docs_dir / f"{stage_id}.md").write_text(
            md,
            encoding="utf-8",
        )
        (args.graph_dir / f"{stage_id}_graph.json").write_text(
            json.dumps(graph, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest = {
            "stage_id": stage_id,
            "registry": str(args.registry),
            "graphify_json": str(args.graphify_json) if args.graphify_json else "",
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["links"]),
            "scope": graph["scope"],
        }
        (args.graph_dir / f"{stage_id}_scope_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        index_lines.append(f"- [{stage.title}]({stage_id}.md)")

    args.docs_dir.joinpath("index.md").write_text(
        "\n".join(index_lines) + "\n",
        encoding="utf-8",
    )

    print("process stage docs PASS")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Validate scoped process graphs against the executable stage registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.behemoth.ops.process_graph import validate_stage_graph  # noqa: E402
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
        "--graph",
        nargs=2,
        action="append",
        metavar=("STAGE_ID", "GRAPH_JSON"),
        default=[],
        help="Validate one scoped graph JSON for one stage. Repeatable.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry = load_stage_registry(args.registry)
    graph_specs: list[tuple[str, Path]] = [(stage, Path(path)) for stage, path in args.graph]
    if not graph_specs:
        graph_specs = [
            (
                stage_id,
                Path("data/analysis/process_graph") / f"{stage_id}_graph.json",
            )
            for stage_id in sorted(registry.stages)
        ]

    issues: list[dict[str, str]] = []
    for stage_id, graph_path in graph_specs:
        stage = registry.require_stage(stage_id)
        if not graph_path.exists():
            issues.append(
                {
                    "stage_id": stage_id,
                    "code": "missing_graph",
                    "detail": str(graph_path),
                }
            )
            continue
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        issues.extend(validate_stage_graph(stage, graph))

    if issues:
        for issue in issues:
            print(f"{issue['stage_id']}: {issue['code']}: {issue['detail']}")
        raise SystemExit(1)

    print("process graph contract PASS")


if __name__ == "__main__":
    main()

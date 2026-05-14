#!/usr/bin/env python3
"""Regenerate CONTEXT.md god nodes and communities sections from graphify output."""

import json
from pathlib import Path


def extract_god_nodes(graph_report: dict) -> list[tuple[str, int]]:
    """Extract god nodes (most connected) from graphify report."""
    # Try to get god_nodes field first (legacy format)
    god_nodes = graph_report.get("god_nodes", [])
    if god_nodes:
        return [(node["name"], node["edges"]) for node in god_nodes[:9]]

    # Compute from graph structure: find nodes with highest degree
    if "nodes" not in graph_report or "links" not in graph_report:
        return []

    nodes = graph_report["nodes"]
    links = graph_report["links"]

    # Count edges per node (skip obvious non-core nodes like JS libraries)
    degree = {}
    for node in nodes:
        node_id = node["id"]
        # Skip JS files and other noise
        if node_id.endswith(".min.js") or node_id.startswith("lunr"):
            continue
        degree[node_id] = 0

    for link in links:
        src, tgt = link.get("source"), link.get("target")
        if src in degree:
            degree[src] += 1
        if tgt in degree:
            degree[tgt] += 1

    # Sort by degree and get node labels
    sorted_nodes = sorted(degree.items(), key=lambda x: x[1], reverse=True)[:9]

    # Map node IDs back to labels
    id_to_label = {n["id"]: n.get("label", n["id"]) for n in nodes}

    return [(id_to_label.get(node_id, node_id), edges) for node_id, edges in sorted_nodes]


def extract_communities(graph_report: dict) -> list[dict]:
    """Extract community information from graphify report."""
    communities = graph_report.get("communities", [])
    return communities


def generate_god_nodes_section(god_nodes: list[tuple[str, int]]) -> str:
    """Generate markdown for god nodes section."""
    lines = [
        "**God Nodes** (most-connected, touch many modules):\n",
    ]

    for i, (name, edges) in enumerate(god_nodes, 1):
        lines.append(f"{i}. **`{name}`** ({edges} edges)")

    return "\n".join(lines)


def load_graph_report() -> dict:
    """Load graphify GRAPH_REPORT.md and extract JSON."""
    report_path = Path("graphify-out/GRAPH_REPORT.md")
    if not report_path.exists():
        raise FileNotFoundError(f"{report_path} not found")

    with open(report_path) as f:
        f.read()

    # Try to find JSON in the report (graphify embeds metadata)
    graph_json_path = Path("graphify-out/graph.json")
    if graph_json_path.exists():
        with open(graph_json_path) as f:
            graph = json.load(f)
            return graph

    raise FileNotFoundError("graphify-out/graph.json not found")


def update_context_md(god_nodes_section: str) -> None:
    """Update CONTEXT.md with regenerated sections."""
    context_path = Path("CONTEXT.md")

    if not context_path.exists():
        print(f"WARNING: {context_path} not found. Skipping regeneration.")
        return

    with open(context_path) as f:
        content = f.read()

    # Replace God Nodes section (between markers)
    god_nodes_start = content.find("**God Nodes** (most-connected")
    if god_nodes_start == -1:
        print("WARNING: Could not find God Nodes section in CONTEXT.md. Skipping.")
        return

    # Find the end of the god nodes section (next ## or ***)
    god_nodes_end = content.find("\n\n**Major Communities**", god_nodes_start)
    if god_nodes_end == -1:
        god_nodes_end = content.find("\n\n### ", god_nodes_start)

    if god_nodes_end == -1:
        print("WARNING: Could not find end of God Nodes section. Skipping.")
        return

    # Replace the section
    new_content = (
        content[:god_nodes_start]
        + god_nodes_section
        + content[god_nodes_end:]
    )

    with open(context_path, "w") as f:
        f.write(new_content)

    print("✓ Updated CONTEXT.md: God Nodes section regenerated")


def main() -> None:
    """Main entry point."""
    try:
        graph = load_graph_report()

        # Extract data
        god_nodes = extract_god_nodes(graph)

        if not god_nodes:
            print("WARNING: No god nodes found in graphify output.")
            return

        # Generate sections
        god_nodes_section = generate_god_nodes_section(god_nodes)

        # Update CONTEXT.md
        update_context_md(god_nodes_section)

        print(f"✓ Regenerated CONTEXT.md from graphify output ({len(god_nodes)} god nodes)")

    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        exit(1)


if __name__ == "__main__":
    main()

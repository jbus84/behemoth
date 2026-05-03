from __future__ import annotations

import fnmatch
import json
from collections import deque
from pathlib import Path
from typing import Any

from src.behemoth.ops.process_registry import StageSpec


class GraphScopeError(ValueError):
    pass


def _as_posix(path: str | Path) -> str:
    return Path(str(path)).as_posix().lstrip("./")


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _is_allowed(stage: StageSpec, path: str) -> bool:
    cleaned = _as_posix(path)
    if _matches(cleaned, stage.graphify.deny):
        return False
    if not stage.graphify.allow:
        return True
    return _matches(cleaned, stage.graphify.allow)


def _relpath_for_source(source_file: str, *, repo_root: Path) -> str:
    raw = Path(str(source_file))
    try:
        return raw.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        pass

    parts = raw.parts
    if ".worktrees" in parts:
        idx = parts.index(".worktrees")
        return Path(*parts[idx:]).as_posix()
    repo_name = repo_root.name
    if repo_name in parts:
        idx = len(parts) - 1 - list(reversed(parts)).index(repo_name)
        if idx + 1 < len(parts):
            return Path(*parts[idx + 1 :]).as_posix()
    return raw.as_posix().lstrip("/")


def _node_id_for_path(path: str) -> str:
    return (
        _as_posix(path)
        .replace("/", "__")
        .replace(".", "_")
        .replace("-", "_")
        .replace(" ", "_")
    )


def _load_graphify_payload(graphify_json: Path | None) -> dict[str, Any]:
    if graphify_json is None or not graphify_json.exists():
        return {"nodes": [], "links": []}
    return json.loads(graphify_json.read_text(encoding="utf-8"))


def _graphify_nodes_by_id(
    stage: StageSpec, payload: dict[str, Any], *, repo_root: Path
) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for raw in payload.get("nodes", []):
        if not isinstance(raw, dict):
            continue
        node_id = str(raw.get("id", "")).strip()
        source_file = str(raw.get("source_file") or raw.get("path") or "").strip()
        if not node_id or not source_file:
            continue
        relpath = _relpath_for_source(source_file, repo_root=repo_root)
        if not _is_allowed(stage, relpath):
            continue
        nodes[node_id] = {
            "id": node_id,
            "path": relpath,
            "label": str(raw.get("label") or Path(relpath).name),
            "source": "graphify",
        }
    return nodes


def _graphify_links(
    stage: StageSpec,
    payload: dict[str, Any],
    allowed_nodes: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    allowed_edge_types = set(stage.graphify.edge_types)
    out: list[dict[str, str]] = []
    for raw in payload.get("links", []):
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source", "")).strip()
        target = str(raw.get("target", "")).strip()
        edge_type = str(raw.get("type") or raw.get("edge_type") or "related").strip()
        if allowed_edge_types and edge_type not in allowed_edge_types:
            continue
        if source in allowed_nodes and target in allowed_nodes:
            out.append({"source": source, "target": target, "type": edge_type})
    return out


def _reachable_graphify_ids(
    stage: StageSpec,
    nodes: dict[str, dict[str, Any]],
    links: list[dict[str, str]],
) -> set[str]:
    seed_paths = {_as_posix(seed) for seed in stage.graphify.seeds}
    seed_ids = {node_id for node_id, node in nodes.items() if node["path"] in seed_paths}
    if not seed_ids:
        return set()

    adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for link in links:
        source = link["source"]
        target = link["target"]
        adjacency.setdefault(source, set()).add(target)
        adjacency.setdefault(target, set()).add(source)

    seen = set(seed_ids)
    queue: deque[tuple[str, int]] = deque((node_id, 0) for node_id in seed_ids)
    while queue:
        node_id, depth = queue.popleft()
        if depth >= stage.graphify.max_depth:
            continue
        for neighbor in adjacency.get(node_id, set()):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            queue.append((neighbor, depth + 1))
    return seen


def build_stage_graph(
    stage: StageSpec,
    *,
    repo_root: Path,
    graphify_json: Path | None = None,
) -> dict[str, Any]:
    payload = _load_graphify_payload(graphify_json)
    graphify_nodes = _graphify_nodes_by_id(stage, payload, repo_root=repo_root)
    graphify_links = _graphify_links(stage, payload, graphify_nodes)
    reachable = _reachable_graphify_ids(stage, graphify_nodes, graphify_links)

    nodes_by_path: dict[str, dict[str, str]] = {}
    for seed in stage.graphify.seeds:
        path = _as_posix(seed)
        if _is_allowed(stage, path):
            nodes_by_path[path] = {
                "id": _node_id_for_path(path),
                "path": path,
                "label": Path(path).name,
                "source": "registry",
            }

    graphify_id_to_scoped_id: dict[str, str] = {}
    for node_id in sorted(reachable):
        node = graphify_nodes[node_id]
        path = node["path"]
        scoped_id = _node_id_for_path(path)
        graphify_id_to_scoped_id[node_id] = scoped_id
        nodes_by_path[path] = {
            "id": scoped_id,
            "path": path,
            "label": str(node["label"]),
            "source": "graphify",
        }

    links: list[dict[str, str]] = []
    seen_links: set[tuple[str, str, str]] = set()
    for link in graphify_links:
        if link["source"] not in reachable or link["target"] not in reachable:
            continue
        scoped = (
            graphify_id_to_scoped_id[link["source"]],
            graphify_id_to_scoped_id[link["target"]],
            link["type"],
        )
        if scoped in seen_links:
            continue
        seen_links.add(scoped)
        links.append({"source": scoped[0], "target": scoped[1], "type": scoped[2]})

    nodes = sorted(nodes_by_path.values(), key=lambda item: item["path"])
    if len(nodes) > stage.graphify.max_nodes:
        raise GraphScopeError(
            f"{stage.stage_id}: scoped graph exceeds node budget "
            f"({len(nodes)} > {stage.graphify.max_nodes})"
        )
    if len(links) > stage.graphify.max_edges:
        raise GraphScopeError(
            f"{stage.stage_id}: scoped graph exceeds edge budget "
            f"({len(links)} > {stage.graphify.max_edges})"
        )

    return {
        "scope": {
            "stage_id": stage.stage_id,
            "max_depth": stage.graphify.max_depth,
            "max_nodes": stage.graphify.max_nodes,
            "max_edges": stage.graphify.max_edges,
            "seeds": list(stage.graphify.seeds),
            "allow": list(stage.graphify.allow),
            "deny": list(stage.graphify.deny),
            "edge_types": list(stage.graphify.edge_types),
        },
        "nodes": nodes,
        "links": links,
    }


def validate_stage_graph(stage: StageSpec, graph: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if graph.get("scope", {}).get("stage_id") != stage.stage_id:
        issues.append(
            {
                "stage_id": stage.stage_id,
                "code": "wrong_stage",
                "detail": f"graph is for {graph.get('scope', {}).get('stage_id')!r}",
            }
        )
    nodes = graph.get("nodes", [])
    links = graph.get("links", [])
    node_paths = {str(node.get("path", "")).strip() for node in nodes if isinstance(node, dict)}
    for seed in stage.graphify.seeds:
        if _as_posix(seed) not in node_paths:
            issues.append(
                {
                    "stage_id": stage.stage_id,
                    "code": "missing_seed",
                    "detail": _as_posix(seed),
                }
            )
    for node in nodes:
        if not isinstance(node, dict):
            continue
        path = str(node.get("path", "")).strip()
        if not _is_allowed(stage, path):
            issues.append(
                {
                    "stage_id": stage.stage_id,
                    "code": "denied_path",
                    "detail": path,
                }
            )
    if len(nodes) > stage.graphify.max_nodes:
        issues.append(
            {
                "stage_id": stage.stage_id,
                "code": "node_budget_exceeded",
                "detail": f"{len(nodes)} > {stage.graphify.max_nodes}",
            }
        )
    if len(links) > stage.graphify.max_edges:
        issues.append(
            {
                "stage_id": stage.stage_id,
                "code": "edge_budget_exceeded",
                "detail": f"{len(links)} > {stage.graphify.max_edges}",
            }
        )
    return issues


def render_stage_capsule_markdown(stage: StageSpec, graph: dict[str, Any]) -> str:
    def bullet(items: tuple[str, ...] | list[str]) -> str:
        return "\n".join(f"- `{item}`" for item in items) if items else "- _none declared_"

    gate_lines = [
        f"- `{gate.check_id}`: `{gate.verdict_effect}`, severity `{gate.severity}`"
        for gate in stage.gates.values()
    ]
    node_lines = [
        f"- `{node['path']}` ({node.get('source', 'registry')})" for node in graph.get("nodes", [])
    ]
    return (
        f"# {stage.title}\n\n"
        f"Stage ID: `{stage.stage_id}`\n\n"
        f"{stage.summary}\n\n"
        "## Canonical Commands\n\n"
        f"{bullet(stage.canonical_commands)}\n\n"
        "## Required Inputs\n\n"
        f"{bullet(stage.required_inputs)}\n\n"
        "## Produced Evidence\n\n"
        f"{bullet(stage.produced_evidence)}\n\n"
        "## Gates\n\n"
        f"{chr(10).join(gate_lines)}\n\n"
        "## Implementation Scope\n\n"
        f"{chr(10).join(node_lines) if node_lines else '- _no graph nodes_'}\n\n"
        "## Tests\n\n"
        f"{bullet(stage.tests)}\n"
    )

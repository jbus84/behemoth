from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.behemoth.ops.process_graph import (
    GraphScopeError,
    build_stage_graph,
    render_stage_capsule_markdown,
    validate_stage_graph,
)
from src.behemoth.ops.process_registry import load_stage_registry


def _write_registry(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
stages:
  - stage_id: stage14
    title: Stage 14 JForex Runtime Certification
    summary: Certifies runtime parity for the JForex adapter.
    canonical_commands:
      - make full-stage14-cert
    required_inputs:
      - data/analysis/backtest_reconcile/stage12_stage13_certification_summary.csv
    produced_evidence:
      - data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv
    gates:
      - check_id: local_jforex_surrogate_pass
        verdict_effect: PASS_FAIL
        severity: critical
      - check_id: jforex_outcome_parity_pass
        verdict_effect: MONITOR_ONLY
        severity: monitor
    owning_files:
      - scripts/validate_stage14_jforex_runtime_certification.py
      - scripts/reconcile_jforex_outcomes.py
    tests:
      - tests/test_validate_stage14_jforex_runtime_certification.py
    graphify:
      seeds:
        - scripts/validate_stage14_jforex_runtime_certification.py
        - scripts/reconcile_jforex_outcomes.py
      max_depth: 1
      max_nodes: 5
      max_edges: 10
      allow:
        - scripts/**
        - src/behemoth/**
        - tests/**
      deny:
        - data/**
        - .worktrees/**
        - graphify-out/**
      edge_types:
        - imports
        - calls
""".lstrip(),
        encoding="utf-8",
    )


def _write_graphify_json(path: Path, repo_root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "directed": True,
        "nodes": [
            {
                "id": "validator",
                "label": "validate_stage14_jforex_runtime_certification.py",
                "source_file": str(repo_root / "scripts/validate_stage14_jforex_runtime_certification.py"),
            },
            {
                "id": "api_server",
                "label": "server.py",
                "source_file": str(repo_root / "src/behemoth/api/server.py"),
            },
            {
                "id": "worktree_copy",
                "label": "stale worktree copy",
                "source_file": str(repo_root / ".worktrees/stale/scripts/validate_stage14_jforex_runtime_certification.py"),
            },
            {
                "id": "data_artifact",
                "label": "stage14_jforex_runtime_certification_checks.csv",
                "source_file": str(repo_root / "data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv"),
            },
        ],
        "links": [
            {"source": "validator", "target": "api_server", "type": "imports"},
            {"source": "validator", "target": "data_artifact", "type": "writes_artifact"},
            {"source": "api_server", "target": "worktree_copy", "type": "calls"},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_stage_graph_filters_graphify_to_declared_scope(tmp_path: Path) -> None:
    registry_path = tmp_path / "configs/process/stages.yaml"
    graphify_path = tmp_path / "graphify-out/graph.json"
    _write_registry(registry_path)
    _write_graphify_json(graphify_path, tmp_path)

    stage = load_stage_registry(registry_path).require_stage("stage14")
    graph = build_stage_graph(stage, repo_root=tmp_path, graphify_json=graphify_path)

    node_paths = {node["path"] for node in graph["nodes"]}
    assert "scripts/validate_stage14_jforex_runtime_certification.py" in node_paths
    assert "src/behemoth/api/server.py" in node_paths
    assert all(".worktrees" not in path for path in node_paths)
    assert all(not path.startswith("data/") for path in node_paths)
    assert graph["scope"]["stage_id"] == "stage14"


def test_build_stage_graph_fails_when_scoped_graph_exceeds_budget(tmp_path: Path) -> None:
    registry_path = tmp_path / "configs/process/stages.yaml"
    graphify_path = tmp_path / "graphify-out/graph.json"
    _write_registry(registry_path)
    payload = {
        "nodes": [
            {
                "id": "seed",
                "label": "validate_stage14_jforex_runtime_certification.py",
                "source_file": str(
                    tmp_path / "scripts/validate_stage14_jforex_runtime_certification.py"
                ),
            },
        ]
        + [
            {
                "id": f"n{i}",
                "label": f"file{i}.py",
                "source_file": str(tmp_path / f"scripts/file{i}.py"),
            }
            for i in range(6)
        ],
        "links": [
            {"source": "seed", "target": f"n{i}", "type": "imports"}
            for i in range(6)
        ],
    }
    graphify_path.parent.mkdir(parents=True, exist_ok=True)
    graphify_path.write_text(json.dumps(payload), encoding="utf-8")

    stage = load_stage_registry(registry_path).require_stage("stage14")

    with pytest.raises(GraphScopeError, match="node budget"):
        build_stage_graph(stage, repo_root=tmp_path, graphify_json=graphify_path)


def test_validate_stage_graph_requires_stage_seeds_and_capsule_content(tmp_path: Path) -> None:
    registry_path = tmp_path / "configs/process/stages.yaml"
    _write_registry(registry_path)
    stage = load_stage_registry(registry_path).require_stage("stage14")

    graph = build_stage_graph(stage, repo_root=tmp_path, graphify_json=None)
    issues = validate_stage_graph(stage, graph)
    capsule = render_stage_capsule_markdown(stage, graph)

    assert issues == []
    assert "Stage 14 JForex Runtime Certification" in capsule
    assert "make full-stage14-cert" in capsule
    assert "jforex_outcome_parity_pass" in capsule
    assert "MONITOR_ONLY" in capsule


def test_explain_stage_cli_writes_capsule_and_graph(tmp_path: Path) -> None:
    registry_path = tmp_path / "configs/process/stages.yaml"
    out_dir = tmp_path / "docs/generated/process"
    graph_out = tmp_path / "data/analysis/process_graph/stage14_graph.json"
    _write_registry(registry_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/explain_stage.py",
            "stage14",
            "--registry",
            str(registry_path),
            "--out",
            str(out_dir / "stage14.md"),
            "--graph-out",
            str(graph_out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "wrote" in result.stdout
    assert "Stage 14 JForex Runtime Certification" in (out_dir / "stage14.md").read_text(
        encoding="utf-8"
    )
    assert json.loads(graph_out.read_text(encoding="utf-8"))["scope"]["stage_id"] == "stage14"


def test_build_process_stage_docs_cli_writes_all_registry_stages(tmp_path: Path) -> None:
    registry_path = tmp_path / "configs/process/stages.yaml"
    docs_dir = tmp_path / "docs/generated/process"
    graph_dir = tmp_path / "data/analysis/process_graph"
    _write_registry(registry_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_process_stage_docs.py",
            "--registry",
            str(registry_path),
            "--docs-dir",
            str(docs_dir),
            "--graph-dir",
            str(graph_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "process stage docs PASS" in result.stdout
    assert (docs_dir / "index.md").exists()
    assert (docs_dir / "stage14.md").exists()
    assert (graph_dir / "stage14_graph.json").exists()
    assert json.loads((graph_dir / "stage14_scope_manifest.json").read_text())[
        "stage_id"
    ] == "stage14"


def test_build_process_stage_docs_includes_all_checked_in_stages(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs/generated/process"
    graph_dir = tmp_path / "data/analysis/process_graph"

    subprocess.run(
        [
            sys.executable,
            "scripts/build_process_stage_docs.py",
            "--docs-dir",
            str(docs_dir),
            "--graph-dir",
            str(graph_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    stage_ids = {
        "stage01",
        "stage02",
        "stage03",
        "stage04",
        "stage05",
        "stage06",
        "stage07",
        "stage08",
        "stage09",
        "stage10",
        "stage11",
        "stage12",
        "stage13",
        "stage14",
    }
    for stage_id in stage_ids:
        assert (docs_dir / f"{stage_id}.md").exists()
        assert (graph_dir / f"{stage_id}_graph.json").exists()


def test_validate_process_graph_contract_cli_rejects_denied_graph_node(tmp_path: Path) -> None:
    registry_path = tmp_path / "configs/process/stages.yaml"
    graph_path = tmp_path / "data/analysis/process_graph/stage14_graph.json"
    _write_registry(registry_path)
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps(
            {
                "scope": {"stage_id": "stage14"},
                "nodes": [
                    {
                        "id": "bad",
                        "path": "data/analysis/backtest_reconcile/output.csv",
                        "source": "graphify",
                    }
                ],
                "links": [],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/validate_process_graph_contract.py",
            "--registry",
            str(registry_path),
            "--graph",
            "stage14",
            str(graph_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "denied_path" in result.stdout

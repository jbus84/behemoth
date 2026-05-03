from __future__ import annotations

import json
from pathlib import Path

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
    tests:
      - tests/test_validate_stage14_jforex_runtime_certification.py
    graphify:
      seeds:
        - scripts/validate_stage14_jforex_runtime_certification.py
      max_depth: 2
      max_nodes: 40
      max_edges: 120
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


def test_load_stage_registry_preserves_gate_semantics_and_graphify_scope(tmp_path: Path) -> None:
    registry_path = tmp_path / "configs/process/stages.yaml"
    _write_registry(registry_path)

    registry = load_stage_registry(registry_path)
    stage = registry.require_stage("stage14")

    assert stage.stage_id == "stage14"
    assert stage.canonical_commands == ("make full-stage14-cert",)
    assert stage.gates["local_jforex_surrogate_pass"].verdict_effect == "PASS_FAIL"
    assert stage.gates["jforex_outcome_parity_pass"].verdict_effect == "MONITOR_ONLY"
    assert stage.graphify.max_depth == 2
    assert stage.graphify.deny == ("data/**", ".worktrees/**", "graphify-out/**")


def test_checked_in_stage_registry_contains_stage12_to_stage14_contracts() -> None:
    registry = load_stage_registry(Path("configs/process/stages.yaml"))

    assert set(registry.stages) >= {
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
    assert registry.require_stage("stage01").canonical_commands == ("make rebuild-all",)
    assert registry.require_stage("stage09").canonical_commands == ("make freeze-oco",)
    assert registry.require_stage("stage14").gates["jforex_outcome_parity_pass"].severity == "monitor"
    assert (
        registry.require_stage("stage14").gates["local_jforex_surrogate_pass"].verdict_effect
        == "PASS_FAIL"
    )


def test_stage_registry_can_be_serialized_for_llm_capsules(tmp_path: Path) -> None:
    registry_path = tmp_path / "configs/process/stages.yaml"
    _write_registry(registry_path)

    stage = load_stage_registry(registry_path).require_stage("stage14")
    payload = stage.to_dict()

    assert json.loads(json.dumps(payload))["stage_id"] == "stage14"
    assert payload["graphify"]["seeds"] == [
        "scripts/validate_stage14_jforex_runtime_certification.py"
    ]

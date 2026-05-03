from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class StageGate:
    check_id: str
    verdict_effect: str
    severity: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "verdict_effect": self.verdict_effect,
            "severity": self.severity,
            "description": self.description,
        }


@dataclass(frozen=True)
class GraphifyScope:
    seeds: tuple[str, ...]
    max_depth: int = 1
    max_nodes: int = 300
    max_edges: int = 1500
    allow: tuple[str, ...] = field(default_factory=tuple)
    deny: tuple[str, ...] = field(default_factory=tuple)
    edge_types: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seeds": list(self.seeds),
            "max_depth": self.max_depth,
            "max_nodes": self.max_nodes,
            "max_edges": self.max_edges,
            "allow": list(self.allow),
            "deny": list(self.deny),
            "edge_types": list(self.edge_types),
        }


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    title: str
    summary: str
    canonical_commands: tuple[str, ...]
    required_inputs: tuple[str, ...]
    produced_evidence: tuple[str, ...]
    gates: dict[str, StageGate]
    owning_files: tuple[str, ...]
    tests: tuple[str, ...]
    graphify: GraphifyScope

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "title": self.title,
            "summary": self.summary,
            "canonical_commands": list(self.canonical_commands),
            "required_inputs": list(self.required_inputs),
            "produced_evidence": list(self.produced_evidence),
            "gates": [gate.to_dict() for gate in self.gates.values()],
            "owning_files": list(self.owning_files),
            "tests": list(self.tests),
            "graphify": self.graphify.to_dict(),
        }


@dataclass(frozen=True)
class StageRegistry:
    stages: dict[str, StageSpec]

    def require_stage(self, stage_id: str) -> StageSpec:
        key = str(stage_id).strip()
        try:
            return self.stages[key]
        except KeyError as exc:
            known = ", ".join(sorted(self.stages))
            raise KeyError(f"unknown stage {stage_id!r}; known stages: {known}") from exc


def _strings(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    out: list[str] = []
    for item in value:
        txt = str(item).strip()
        if txt:
            out.append(txt)
    return tuple(out)


def _load_gate(item: dict[str, Any], *, stage_id: str) -> StageGate:
    check_id = str(item.get("check_id", "")).strip()
    if not check_id:
        raise ValueError(f"{stage_id}: gate check_id is required")
    verdict_effect = str(item.get("verdict_effect", "")).strip().upper()
    if verdict_effect not in {"PASS_FAIL", "GO_NO_GO", "MONITOR_ONLY"}:
        raise ValueError(
            f"{stage_id}: {check_id}: verdict_effect must be PASS_FAIL, GO_NO_GO, or MONITOR_ONLY"
        )
    severity = str(item.get("severity", "")).strip().lower()
    if severity not in {"critical", "high", "medium", "low", "monitor"}:
        raise ValueError(f"{stage_id}: {check_id}: invalid severity {severity!r}")
    return StageGate(
        check_id=check_id,
        verdict_effect=verdict_effect,
        severity=severity,
        description=str(item.get("description", "")).strip(),
    )


def _load_graphify_scope(item: dict[str, Any], *, stage_id: str) -> GraphifyScope:
    seeds = _strings(item.get("seeds"), field_name=f"{stage_id}.graphify.seeds")
    if not seeds:
        raise ValueError(f"{stage_id}: graphify.seeds must not be empty")
    max_depth = int(item.get("max_depth", 1))
    if max_depth < 0:
        raise ValueError(f"{stage_id}: graphify.max_depth must be >= 0")
    max_nodes = int(item.get("max_nodes", 300))
    max_edges = int(item.get("max_edges", 1500))
    if max_nodes < len(seeds):
        raise ValueError(f"{stage_id}: graphify.max_nodes must cover all seeds")
    if max_edges < 0:
        raise ValueError(f"{stage_id}: graphify.max_edges must be >= 0")
    return GraphifyScope(
        seeds=seeds,
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_edges=max_edges,
        allow=_strings(item.get("allow"), field_name=f"{stage_id}.graphify.allow"),
        deny=_strings(item.get("deny"), field_name=f"{stage_id}.graphify.deny"),
        edge_types=_strings(item.get("edge_types"), field_name=f"{stage_id}.graphify.edge_types"),
    )


def _load_stage(item: dict[str, Any]) -> StageSpec:
    stage_id = str(item.get("stage_id", "")).strip()
    if not stage_id:
        raise ValueError("stage_id is required")
    gates_payload = item.get("gates", [])
    if not isinstance(gates_payload, list) or not gates_payload:
        raise ValueError(f"{stage_id}: gates must be a non-empty list")
    gates = {
        gate.check_id: gate
        for gate in (_load_gate(raw, stage_id=stage_id) for raw in gates_payload)
    }
    graphify_payload = item.get("graphify", {})
    if not isinstance(graphify_payload, dict):
        raise ValueError(f"{stage_id}: graphify must be a mapping")
    return StageSpec(
        stage_id=stage_id,
        title=str(item.get("title", stage_id)).strip(),
        summary=str(item.get("summary", "")).strip(),
        canonical_commands=_strings(
            item.get("canonical_commands"), field_name=f"{stage_id}.canonical_commands"
        ),
        required_inputs=_strings(item.get("required_inputs"), field_name=f"{stage_id}.inputs"),
        produced_evidence=_strings(
            item.get("produced_evidence"), field_name=f"{stage_id}.produced_evidence"
        ),
        gates=gates,
        owning_files=_strings(item.get("owning_files"), field_name=f"{stage_id}.owning_files"),
        tests=_strings(item.get("tests"), field_name=f"{stage_id}.tests"),
        graphify=_load_graphify_scope(graphify_payload, stage_id=stage_id),
    )


def load_stage_registry(path: Path) -> StageRegistry:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    stages_payload = payload.get("stages", [])
    if not isinstance(stages_payload, list):
        raise ValueError(f"stages must be a list in {path}")
    stages: dict[str, StageSpec] = {}
    for raw_stage in stages_payload:
        if not isinstance(raw_stage, dict):
            raise ValueError(f"stage entries must be mappings in {path}")
        stage = _load_stage(raw_stage)
        if stage.stage_id in stages:
            raise ValueError(f"duplicate stage_id {stage.stage_id!r}")
        stages[stage.stage_id] = stage
    return StageRegistry(stages=stages)

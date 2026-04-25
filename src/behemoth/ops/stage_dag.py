from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.behemoth.ops.verdicts import ProcessVerdict, normalize_process_verdict, normalize_symbol_decision


@dataclass(frozen=True)
class DagValidationIssue:
    node_id: str
    code: str
    detail: str


@dataclass(frozen=True)
class DagNodeSpec:
    node_id: str
    required: bool
    evidence_path: Path
    target_branch: str | None = None
    target_commit: str | None = None
    model_month: str | None = None
    required_outputs: tuple[Path, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DagContract:
    nodes: tuple[DagNodeSpec, ...]


def _repo_path(raw: str | Path) -> Path:
    return raw if isinstance(raw, Path) else Path(str(raw))


def load_dag_contract(path: Path) -> DagContract:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    nodes_payload = payload.get("nodes", [])
    if not isinstance(nodes_payload, list):
        raise ValueError(f"nodes must be a list in {path}")
    nodes: list[DagNodeSpec] = []
    for item in nodes_payload:
        if not isinstance(item, dict):
            raise ValueError(f"node entry must be a mapping in {path}")
        nodes.append(
            DagNodeSpec(
                node_id=str(item["node_id"]),
                required=bool(item.get("required", True)),
                evidence_path=_repo_path(item["evidence_path"]),
                target_branch=(
                    str(item["target_branch"]).strip() if item.get("target_branch") else None
                ),
                target_commit=(
                    str(item["target_commit"]).strip() if item.get("target_commit") else None
                ),
                model_month=str(item["model_month"]).strip() if item.get("model_month") else None,
                required_outputs=tuple(_repo_path(p) for p in item.get("required_outputs", [])),
            )
        )
    return DagContract(nodes=tuple(nodes))


def validate_evidence_for_node(node: DagNodeSpec, *, repo_root: Path) -> list[DagValidationIssue]:
    issues: list[DagValidationIssue] = []
    evidence_path = repo_root / node.evidence_path
    if not evidence_path.exists():
        if node.required:
            issues.append(
                DagValidationIssue(node.node_id, "missing_evidence", str(node.evidence_path))
            )
        return issues
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [DagValidationIssue(node.node_id, "invalid_json", str(exc))]

    if str(evidence.get("dag_node_id", "")).strip() != node.node_id:
        issues.append(
            DagValidationIssue(
                node.node_id,
                "wrong_node_id",
                f"expected {node.node_id}, got {evidence.get('dag_node_id')!r}",
            )
        )
    if node.target_branch and str(evidence.get("target_branch", "")).strip() != node.target_branch:
        issues.append(
            DagValidationIssue(
                node.node_id,
                "wrong_branch",
                f"expected {node.target_branch}, got {evidence.get('target_branch')}",
            )
        )
    if node.target_commit and str(evidence.get("target_commit", "")).strip() != node.target_commit:
        issues.append(
            DagValidationIssue(
                node.node_id,
                "wrong_commit",
                f"expected {node.target_commit}, got {evidence.get('target_commit')}",
            )
        )
    if node.model_month and str(evidence.get("model_month", "")).strip() != node.model_month:
        issues.append(
            DagValidationIssue(
                node.node_id,
                "wrong_model_month",
                f"expected {node.model_month}, got {evidence.get('model_month')}",
            )
        )

    try:
        process_verdict = normalize_process_verdict(str(evidence.get("process_verdict", "")))
    except ValueError as exc:
        issues.append(DagValidationIssue(node.node_id, "invalid_process_verdict", str(exc)))
        process_verdict = ProcessVerdict.FAIL
    if process_verdict is not ProcessVerdict.PASS:
        issues.append(
            DagValidationIssue(node.node_id, "process_not_pass", f"got {process_verdict.value}")
        )

    symbol_decisions = evidence.get("symbol_decisions", {})
    if not isinstance(symbol_decisions, dict) or not symbol_decisions:
        issues.append(DagValidationIssue(node.node_id, "missing_symbol_decisions", "empty or absent"))
    else:
        for symbol, decision in symbol_decisions.items():
            try:
                normalize_symbol_decision(str(decision))
            except ValueError as exc:
                issues.append(
                    DagValidationIssue(
                        node.node_id,
                        "invalid_symbol_decision",
                        f"{symbol}: {exc}",
                    )
                )

    for output in node.required_outputs:
        if not (repo_root / output).exists():
            issues.append(DagValidationIssue(node.node_id, "missing_output", str(output)))
    return issues


def validate_contract(contract: DagContract, *, repo_root: Path) -> list[DagValidationIssue]:
    issues: list[DagValidationIssue] = []
    for node in contract.nodes:
        issues.extend(validate_evidence_for_node(node, repo_root=repo_root))
    return issues

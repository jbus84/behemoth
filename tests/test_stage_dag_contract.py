from __future__ import annotations

import json
from pathlib import Path

from src.behemoth.ops.stage_dag import (
    DagValidationIssue,
    load_dag_contract,
    validate_evidence_for_node,
)


def _write_status(path: Path, *, commit: str = "abc", branch: str = "main") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "dag_node_id": "monthly_recert",
                "model_month": "2026-03",
                "target_branch": branch,
                "target_commit": commit,
                "lock_fingerprint": "fp-1",
                "overall_pass": True,
                "process_verdict": "PASS",
                "symbol_decisions": {
                    "EURUSD": "GO",
                    "AUDUSD": "NO_GO",
                },
                "inputs": {
                    "bundle_dir": "configs/research/governance/oco_candidate_builds/2026-03"
                },
                "outputs": {
                    "checks_csv": "data/analysis/backtest_reconcile/2026-03/monthly_recert/stage14_jforex_runtime_certification_checks.csv",
                    "summary_csv": "data/analysis/backtest_reconcile/2026-03/monthly_recert/stage14_jforex_runtime_certification_summary.csv",
                },
                "evaluated_at_utc": "2026-04-25T10:00:00Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_contract(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
nodes:
  - node_id: monthly_recert
    required: true
    evidence_path: data/analysis/backtest_reconcile/2026-03/monthly_recert/monthly_recert_status.json
    target_branch: main
    target_commit: abc
    model_month: "2026-03"
    required_outputs:
      - data/analysis/backtest_reconcile/2026-03/monthly_recert/stage14_jforex_runtime_certification_checks.csv
      - data/analysis/backtest_reconcile/2026-03/monthly_recert/stage14_jforex_runtime_certification_summary.csv
""".lstrip(),
        encoding="utf-8",
    )


def test_validate_evidence_for_node_accepts_matching_pass_go_nogo(tmp_path: Path) -> None:
    contract_path = tmp_path / "configs/research/governance/live_stage_dag.yaml"
    _write_contract(contract_path)
    status_path = (
        tmp_path
        / "data/analysis/backtest_reconcile/2026-03/monthly_recert/monthly_recert_status.json"
    )
    checks_path = (
        tmp_path
        / "data/analysis/backtest_reconcile/2026-03/monthly_recert/stage14_jforex_runtime_certification_checks.csv"
    )
    summary_path = (
        tmp_path
        / "data/analysis/backtest_reconcile/2026-03/monthly_recert/stage14_jforex_runtime_certification_summary.csv"
    )
    _write_status(status_path)
    checks_path.write_text("symbol,check_id,status,severity\nEURUSD,C1,pass,critical\n")
    summary_path.write_text("symbol,process_status,go_decision\nEURUSD,PASS,GO\nAUDUSD,PASS,NO_GO\n")

    contract = load_dag_contract(contract_path)
    issues = validate_evidence_for_node(contract.nodes[0], repo_root=tmp_path)

    assert issues == []


def test_validate_evidence_for_node_rejects_wrong_branch(tmp_path: Path) -> None:
    contract_path = tmp_path / "configs/research/governance/live_stage_dag.yaml"
    _write_contract(contract_path)
    status_path = (
        tmp_path
        / "data/analysis/backtest_reconcile/2026-03/monthly_recert/monthly_recert_status.json"
    )
    _write_status(status_path, branch="feature")

    contract = load_dag_contract(contract_path)
    issues = validate_evidence_for_node(contract.nodes[0], repo_root=tmp_path)

    assert DagValidationIssue(
        node_id="monthly_recert",
        code="wrong_branch",
        detail="expected main, got feature",
    ) in issues


def test_validate_evidence_for_node_rejects_fail_process_even_with_no_go_symbol(
    tmp_path: Path,
) -> None:
    contract_path = tmp_path / "configs/research/governance/live_stage_dag.yaml"
    _write_contract(contract_path)
    status_path = (
        tmp_path
        / "data/analysis/backtest_reconcile/2026-03/monthly_recert/monthly_recert_status.json"
    )
    _write_status(status_path)
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    payload["process_verdict"] = "FAIL"
    payload["symbol_decisions"] = {"EURUSD": "NO_GO"}
    status_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    contract = load_dag_contract(contract_path)
    issues = validate_evidence_for_node(contract.nodes[0], repo_root=tmp_path)

    assert any(issue.code == "process_not_pass" for issue in issues)

# Live Stage Commonality DAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repo-native DAG/provenance validation and explicit restart eligibility so promotion and live restart cannot silently use wrong branch, stale evidence, wrong lock, or unsafe preserved state.

**Architecture:** Keep live trading supervised by the existing live runner. Add small shared Python primitives for verdict semantics, a repo-native DAG contract validator, stronger monthly recert provenance, promotion-time DAG validation, and an explicit restart eligibility result that can block, resume normally, or resume with new entries disabled. Add a Java global no-new-entries gate so Python restart eligibility can enforce drain-only live startup.

**Tech Stack:** Python 3.12, pytest, PyYAML, DuckDB, existing `uv run` workflow, Java 17/JUnit 5/Gradle under `src/jforex`.

---

## Scope

This is the first implementation PR for the approved design. It implements the repository-native hardening layer and restart eligibility. It does not add Prefect. Prefect remains a later execution backend after the graph contract is validated locally.

## File Structure

- Create: `src/behemoth/ops/__init__.py`
- Create: `src/behemoth/ops/verdicts.py`
- Create: `src/behemoth/ops/stage_dag.py`
- Create: `configs/research/governance/live_stage_dag.yaml`
- Create: `scripts/validate_live_stage_dag.py`
- Create: `tests/test_ops_verdicts.py`
- Create: `tests/test_stage_dag_contract.py`
- Modify: `scripts/run_monthly_recert.py`
- Modify: `scripts/run_promote_live.py`
- Modify: `scripts/run_jforex_live.py`
- Modify: `src/behemoth/live_restart/reconciliation.py`
- Modify: `tests/test_run_monthly_recert.py`
- Modify: `tests/test_run_promote_live.py`
- Modify: `tests/test_live_restart_reconciliation.py`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessCoordinatorTest.java`
- Modify: `Makefile`

## Task 1: Shared Verdict Semantics

**Files:**
- Create: `src/behemoth/ops/__init__.py`
- Create: `src/behemoth/ops/verdicts.py`
- Test: `tests/test_ops_verdicts.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ops_verdicts.py`:

```python
from __future__ import annotations

import pytest

from src.behemoth.ops.verdicts import (
    ProcessVerdict,
    RestartEligibility,
    SymbolDecision,
    normalize_process_verdict,
    normalize_restart_eligibility,
    normalize_symbol_decision,
)


def test_process_verdict_accepts_only_pass_or_fail() -> None:
    assert normalize_process_verdict("PASS") is ProcessVerdict.PASS
    assert normalize_process_verdict("fail") is ProcessVerdict.FAIL

    with pytest.raises(ValueError, match="process verdict"):
        normalize_process_verdict("NO_GO")


def test_symbol_decision_accepts_only_go_or_no_go() -> None:
    assert normalize_symbol_decision("GO") is SymbolDecision.GO
    assert normalize_symbol_decision("no-go") is SymbolDecision.NO_GO

    with pytest.raises(ValueError, match="symbol decision"):
        normalize_symbol_decision("FAIL")


def test_restart_eligibility_names_are_operator_facing() -> None:
    assert normalize_restart_eligibility("restart_eligible") is RestartEligibility.RESTART_ELIGIBLE
    assert (
        normalize_restart_eligibility("RESTART_ELIGIBLE_DRAIN_ONLY")
        is RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY
    )
    assert normalize_restart_eligibility("blocked") is RestartEligibility.RESTART_BLOCKED

    with pytest.raises(ValueError, match="restart eligibility"):
        normalize_restart_eligibility("clean_resumable")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest -q tests/test_ops_verdicts.py
```

Expected: import failure because `src.behemoth.ops.verdicts` does not exist.

- [ ] **Step 3: Add the implementation**

Create `src/behemoth/ops/__init__.py`:

```python
"""Operational process contracts shared by certification, promotion, and live startup."""
```

Create `src/behemoth/ops/verdicts.py`:

```python
from __future__ import annotations

from enum import Enum


class ProcessVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class SymbolDecision(str, Enum):
    GO = "GO"
    NO_GO = "NO_GO"


class RestartEligibility(str, Enum):
    RESTART_ELIGIBLE = "RESTART_ELIGIBLE"
    RESTART_ELIGIBLE_DRAIN_ONLY = "RESTART_ELIGIBLE_DRAIN_ONLY"
    RESTART_BLOCKED = "RESTART_BLOCKED"


def _clean(value: str) -> str:
    return str(value).strip().upper().replace("-", "_")


def normalize_process_verdict(value: str) -> ProcessVerdict:
    cleaned = _clean(value)
    if cleaned == "PASS":
        return ProcessVerdict.PASS
    if cleaned == "FAIL":
        return ProcessVerdict.FAIL
    raise ValueError(f"invalid process verdict: {value!r}; expected PASS or FAIL")


def normalize_symbol_decision(value: str) -> SymbolDecision:
    cleaned = _clean(value)
    if cleaned == "GO":
        return SymbolDecision.GO
    if cleaned in {"NO_GO", "NOGO"}:
        return SymbolDecision.NO_GO
    raise ValueError(f"invalid symbol decision: {value!r}; expected GO or NO_GO")


def normalize_restart_eligibility(value: str) -> RestartEligibility:
    cleaned = _clean(value)
    if cleaned in {"RESTART_ELIGIBLE", "ELIGIBLE"}:
        return RestartEligibility.RESTART_ELIGIBLE
    if cleaned in {"RESTART_ELIGIBLE_DRAIN_ONLY", "DRAIN_ONLY"}:
        return RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY
    if cleaned in {"RESTART_BLOCKED", "BLOCKED"}:
        return RestartEligibility.RESTART_BLOCKED
    raise ValueError(
        f"invalid restart eligibility: {value!r}; expected RESTART_ELIGIBLE, "
        "RESTART_ELIGIBLE_DRAIN_ONLY, or RESTART_BLOCKED"
    )
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
uv run pytest -q tests/test_ops_verdicts.py
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/ops/__init__.py src/behemoth/ops/verdicts.py tests/test_ops_verdicts.py
git commit -m "Add shared operational verdict enums"
```

## Task 2: DAG Contract Model And Validator

**Files:**
- Create: `src/behemoth/ops/stage_dag.py`
- Create: `configs/research/governance/live_stage_dag.yaml`
- Create: `scripts/validate_live_stage_dag.py`
- Test: `tests/test_stage_dag_contract.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_stage_dag_contract.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest -q tests/test_stage_dag_contract.py
```

Expected: import failure because `src.behemoth.ops.stage_dag` does not exist.

- [ ] **Step 3: Add the DAG model**

Create `src/behemoth/ops/stage_dag.py`:

```python
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
```

- [ ] **Step 4: Add the repository contract file**

Create `configs/research/governance/live_stage_dag.yaml`:

```yaml
nodes:
  - node_id: monthly_recert
    required: true
    evidence_path: data/analysis/backtest_reconcile/${MODEL_MONTH}/monthly_recert/monthly_recert_status.json
    target_branch: main
    model_month: ${MODEL_MONTH}
    required_outputs:
      - data/analysis/backtest_reconcile/${MODEL_MONTH}/monthly_recert/stage14_jforex_runtime_certification_checks.csv
      - data/analysis/backtest_reconcile/${MODEL_MONTH}/monthly_recert/stage14_jforex_runtime_certification_summary.csv
```

The `${MODEL_MONTH}` values in this YAML are literal substitution tokens for the CLI in the next step.

- [ ] **Step 5: Add the CLI**

Create `scripts/validate_live_stage_dag.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_REPO_ROOT))

from src.behemoth.ops.stage_dag import load_dag_contract, validate_contract


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _materialize_contract(src: Path, *, model_month: str, target_commit: str | None) -> Path:
    text = src.read_text(encoding="utf-8").replace("${MODEL_MONTH}", model_month)
    if target_commit:
        text = text.replace("${TARGET_COMMIT}", target_commit)
    tmp_path = src.parent / f".{src.stem}.{model_month}.materialized.yaml"
    tmp_path.write_text(text, encoding="utf-8")
    return tmp_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default="configs/research/governance/live_stage_dag.yaml")
    parser.add_argument("--model-month", required=True)
    parser.add_argument("--target-commit", default="")
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()

    repo_root = _repo_root()
    contract_path = repo_root / args.contract
    materialized = _materialize_contract(
        contract_path,
        model_month=str(args.model_month),
        target_commit=str(args.target_commit).strip() or None,
    )
    try:
        contract = load_dag_contract(materialized)
        issues = validate_contract(contract, repo_root=repo_root)
    finally:
        materialized.unlink(missing_ok=True)

    payload = {
        "ok": not issues,
        "model_month": str(args.model_month),
        "issues": [issue.__dict__ for issue in issues],
    }
    if args.out_json:
        out_path = repo_root / args.out_json
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests and verify pass**

Run:

```bash
uv run pytest -q tests/test_stage_dag_contract.py
```

Expected: `3 passed`.

- [ ] **Step 7: Commit**

```bash
git add src/behemoth/ops/stage_dag.py configs/research/governance/live_stage_dag.yaml scripts/validate_live_stage_dag.py tests/test_stage_dag_contract.py
git commit -m "Add live stage DAG contract validator"
```

## Task 3: Monthly Recert Provenance Status

**Files:**
- Modify: `scripts/run_monthly_recert.py`
- Modify: `tests/test_run_monthly_recert.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_run_monthly_recert.py`:

```python
def test_write_recert_status_records_dag_provenance(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_monthly_recert, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        run_monthly_recert,
        "_git_metadata",
        lambda: ("abc123", "main", False),
    )
    monkeypatch.setattr(run_monthly_recert, "_lock_fingerprint", lambda path: "fp-1")

    report_dir = "data/analysis/backtest_reconcile/2026-03/monthly_recert"
    summary_dir = tmp_path / report_dir
    summary_dir.mkdir(parents=True)
    (summary_dir / run_monthly_recert.CERT_SUMMARY_FILENAME).write_text(
        "symbol,process_status,go_decision\nEURUSD,PASS,GO\nAUDUSD,PASS,NO_GO\n",
        encoding="utf-8",
    )

    run_monthly_recert._write_recert_status(
        "2026-03",
        report_dir,
        run_monthly_recert.Path("configs/research/governance/oco_candidate_builds/2026-03"),
        True,
    )

    payload = json.loads(
        (summary_dir / run_monthly_recert.MONTHLY_RECERT_STATUS_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert payload["dag_node_id"] == "monthly_recert"
    assert payload["target_branch"] == "main"
    assert payload["target_commit"] == "abc123"
    assert payload["git_dirty"] is False
    assert payload["process_verdict"] == "PASS"
    assert payload["symbol_decisions"] == {"AUDUSD": "NO_GO", "EURUSD": "GO"}
    assert payload["lock_fingerprint"] == "fp-1"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run pytest -q tests/test_run_monthly_recert.py::test_write_recert_status_records_dag_provenance
```

Expected: failure because `_git_metadata`, `_lock_fingerprint`, and new status fields are absent.

- [ ] **Step 3: Add provenance helpers**

Add imports near the top of `scripts/run_monthly_recert.py`:

```python
import hashlib
```

Add helpers below `_repo_root()`:

```python
def _git_metadata() -> tuple[str, str, bool]:
    repo_root = _repo_root()
    commit = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    branch = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return commit, branch, dirty


def _lock_fingerprint(bundle_dir: Path) -> str:
    root = bundle_dir if bundle_dir.is_absolute() else _repo_root() / bundle_dir
    digest = hashlib.sha256()
    for path in sorted(root.glob("*_oco_live_lock.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _read_symbol_decisions(report_dir: str) -> dict[str, str]:
    summary_path = _repo_root() / report_dir / CERT_CHECKS_FILENAME.replace(
        "_checks.csv",
        "_summary.csv",
    )
    if not summary_path.exists():
        return {}
    decisions: dict[str, str] = {}
    with summary_path.open() as f:
        for row in csv.DictReader(f):
            symbol = str(row.get("symbol", "")).strip().upper()
            decision = str(row.get("go_decision", "")).strip().upper().replace("-", "_")
            if symbol:
                decisions[symbol] = "NO_GO" if decision in {"NOGO", "NO_GO"} else decision
    return dict(sorted(decisions.items()))
```

- [ ] **Step 4: Update `_write_recert_status`**

Before `status_path.write_text(...)`, assign git metadata once:

```python
    commit, branch, dirty = _git_metadata()
```

Replace the JSON payload inside `_write_recert_status()` with:

```python
            {
                "dag_node_id": "monthly_recert",
                "model_month": model_month,
                "bundle_dir": str((_repo_root() / bundle_dir).resolve()),
                "overall_pass": bool(overall_pass),
                "process_verdict": "PASS" if overall_pass else "FAIL",
                "symbol_decisions": _read_symbol_decisions(report_dir),
                "target_branch": branch,
                "target_commit": commit,
                "git_dirty": dirty,
                "lock_fingerprint": _lock_fingerprint(_repo_root() / bundle_dir),
                "inputs": {
                    "bundle_dir": str((_repo_root() / bundle_dir).resolve()),
                    "lock_dir": str((_repo_root() / bundle_dir).resolve()),
                },
                "outputs": {
                    "checks_csv": str((_repo_root() / report_dir / CERT_CHECKS_FILENAME).resolve()),
                    "summary_csv": str(
                        (
                            _repo_root()
                            / report_dir
                            / CERT_CHECKS_FILENAME.replace("_checks.csv", "_summary.csv")
                        ).resolve()
                    ),
                },
                "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
```

- [ ] **Step 5: Run targeted tests and verify pass**

Run:

```bash
uv run pytest -q tests/test_run_monthly_recert.py
```

Expected: all tests in `tests/test_run_monthly_recert.py` pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_monthly_recert.py tests/test_run_monthly_recert.py
git commit -m "Record monthly recert DAG provenance"
```

## Task 4: Promotion-Time DAG Validation

**Files:**
- Modify: `scripts/run_promote_live.py`
- Modify: `tests/test_run_promote_live.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_run_promote_live.py`:

```python
def test_verify_cert_requires_dag_provenance_fields(tmp_path) -> None:
    report_dir = tmp_path / "data/analysis/backtest_reconcile"
    report_dir.mkdir(parents=True)
    today = f"{date.today().isoformat()}T12:00:00Z"
    (report_dir / run_promote_live.CERT_CHECKS_FILENAME).write_text(
        f"symbol,check_id,status,severity,evaluated_at_utc\nEURUSD,C1,pass,critical,{today}\n",
        encoding="utf-8",
    )
    (report_dir / run_promote_live.MONTHLY_RECERT_STATUS_FILENAME).write_text(
        json.dumps(
            {
                "model_month": "2026-03",
                "evaluated_at_utc": today,
                "overall_pass": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match=r"missing DAG provenance"):
        run_promote_live._verify_cert(
            "data/analysis/backtest_reconcile",
            "2026-03",
            repo_root=tmp_path,
        )


def test_verify_cert_rejects_wrong_branch_provenance(tmp_path) -> None:
    report_dir = tmp_path / "data/analysis/backtest_reconcile"
    report_dir.mkdir(parents=True)
    today = f"{date.today().isoformat()}T12:00:00Z"
    (report_dir / run_promote_live.CERT_CHECKS_FILENAME).write_text(
        f"symbol,check_id,status,severity,evaluated_at_utc\nEURUSD,C1,pass,critical,{today}\n",
        encoding="utf-8",
    )
    (report_dir / run_promote_live.MONTHLY_RECERT_STATUS_FILENAME).write_text(
        json.dumps(
            {
                "dag_node_id": "monthly_recert",
                "model_month": "2026-03",
                "evaluated_at_utc": today,
                "overall_pass": True,
                "process_verdict": "PASS",
                "target_branch": "feature",
                "target_commit": "abc123",
                "git_dirty": False,
                "symbol_decisions": {"EURUSD": "GO"},
                "lock_fingerprint": "fp-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match=r"target_branch.*main"):
        run_promote_live._verify_cert(
            "data/analysis/backtest_reconcile",
            "2026-03",
            repo_root=tmp_path,
        )
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest -q tests/test_run_promote_live.py::test_verify_cert_requires_dag_provenance_fields tests/test_run_promote_live.py::test_verify_cert_rejects_wrong_branch_provenance
```

Expected: failures because `_verify_cert()` does not require DAG provenance fields.

- [ ] **Step 3: Add provenance validation**

Add this helper to `scripts/run_promote_live.py` above `_verify_cert()`:

```python
def _verify_dag_provenance(status: dict[str, object], model_month: str) -> None:
    required = {
        "dag_node_id",
        "model_month",
        "process_verdict",
        "target_branch",
        "target_commit",
        "git_dirty",
        "symbol_decisions",
        "lock_fingerprint",
    }
    missing = sorted(key for key in required if key not in status)
    if missing:
        raise SystemExit(
            "[promote-live] missing DAG provenance in monthly recert status: "
            + ",".join(missing)
        )
    if str(status["dag_node_id"]) != "monthly_recert":
        raise SystemExit(f"[promote-live] unexpected DAG node id: {status['dag_node_id']}")
    if str(status["model_month"]) != model_month:
        raise SystemExit(
            f"[promote-live] cert status month mismatch: requested {model_month}, got {status['model_month']}"
        )
    if str(status["process_verdict"]).upper() != "PASS":
        raise SystemExit("[promote-live] monthly recert process_verdict is not PASS")
    if str(status["target_branch"]) != "main":
        raise SystemExit(
            f"[promote-live] target_branch must be main for promotion, got {status['target_branch']}"
        )
    if bool(status["git_dirty"]):
        raise SystemExit("[promote-live] monthly recert was produced from dirty git state")
    if not isinstance(status["symbol_decisions"], dict) or not status["symbol_decisions"]:
        raise SystemExit("[promote-live] monthly recert symbol_decisions missing or empty")
```

Inside `_verify_cert()`, after loading `status`, call:

```python
    _verify_dag_provenance(status, model_month)
```

Keep the existing date staleness checks. They still protect operator freshness separately from DAG provenance.

- [ ] **Step 4: Update existing tests that create status JSON**

Every existing test fixture in `tests/test_run_promote_live.py` that expects `_verify_cert()` to pass must include:

```python
{
    "dag_node_id": "monthly_recert",
    "process_verdict": "PASS",
    "target_branch": "main",
    "target_commit": "abc123",
    "git_dirty": False,
    "symbol_decisions": {"EURUSD": "GO"},
    "lock_fingerprint": "fp-1",
}
```

For tests with `AUDUSD,NO_GO`, set:

```python
"symbol_decisions": {"EURUSD": "GO", "AUDUSD": "NO_GO"}
```

- [ ] **Step 5: Run targeted tests and verify pass**

Run:

```bash
uv run pytest -q tests/test_run_promote_live.py
```

Expected: all tests in `tests/test_run_promote_live.py` pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_promote_live.py tests/test_run_promote_live.py
git commit -m "Require DAG provenance for live promotion"
```

## Task 5: Explicit Restart Eligibility

**Files:**
- Modify: `src/behemoth/live_restart/reconciliation.py`
- Modify: `scripts/run_jforex_live.py`
- Modify: `tests/test_live_restart_reconciliation.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_live_restart_reconciliation.py`:

```python
from src.behemoth.ops.verdicts import RestartEligibility
```

Add tests:

```python
def test_derive_restart_eligibility_maps_clean_resume_to_eligible() -> None:
    from src.behemoth.live_restart.reconciliation import derive_restart_eligibility

    result = derive_restart_eligibility(
        RuntimeContextComparison(verdict=RestartVerdict.CLEAN_RESUMABLE, reasons=[])
    )

    assert result.eligibility is RestartEligibility.RESTART_ELIGIBLE
    assert result.allow_new_entries is True


def test_derive_restart_eligibility_maps_reconcilable_to_drain_only() -> None:
    from src.behemoth.live_restart.reconciliation import derive_restart_eligibility

    result = derive_restart_eligibility(
        RuntimeContextComparison(
            verdict=RestartVerdict.RECONCILABLE,
            reasons=["local runtime has recoverable active state"],
        )
    )

    assert result.eligibility is RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY
    assert result.allow_new_entries is False
    assert result.reasons == ["local runtime has recoverable active state"]


def test_derive_restart_eligibility_maps_incompatible_to_blocked() -> None:
    from src.behemoth.live_restart.reconciliation import derive_restart_eligibility

    result = derive_restart_eligibility(
        RuntimeContextComparison(
            verdict=RestartVerdict.INCOMPATIBLE,
            reasons=["lock_fingerprint mismatch"],
        )
    )

    assert result.eligibility is RestartEligibility.RESTART_BLOCKED
    assert result.allow_new_entries is False
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest -q tests/test_live_restart_reconciliation.py::test_derive_restart_eligibility_maps_clean_resume_to_eligible tests/test_live_restart_reconciliation.py::test_derive_restart_eligibility_maps_reconcilable_to_drain_only tests/test_live_restart_reconciliation.py::test_derive_restart_eligibility_maps_incompatible_to_blocked
```

Expected: import failure because `derive_restart_eligibility` does not exist.

- [ ] **Step 3: Add restart eligibility dataclass and mapper**

Modify `src/behemoth/live_restart/reconciliation.py` imports:

```python
from src.behemoth.ops.verdicts import RestartEligibility
```

Add below `RuntimeContextComparison`:

```python
@dataclass(frozen=True)
class RestartEligibilityResult:
    eligibility: RestartEligibility
    allow_new_entries: bool
    reasons: list[str] = field(default_factory=list)
```

Add below `compare_runtime_context()`:

```python
def derive_restart_eligibility(
    comparison: RuntimeContextComparison,
) -> RestartEligibilityResult:
    if comparison.verdict is RestartVerdict.CLEAN_RESUMABLE:
        return RestartEligibilityResult(
            eligibility=RestartEligibility.RESTART_ELIGIBLE,
            allow_new_entries=True,
            reasons=list(comparison.reasons),
        )
    if comparison.verdict is RestartVerdict.RECONCILABLE:
        return RestartEligibilityResult(
            eligibility=RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY,
            allow_new_entries=False,
            reasons=list(comparison.reasons),
        )
    return RestartEligibilityResult(
        eligibility=RestartEligibility.RESTART_BLOCKED,
        allow_new_entries=False,
        reasons=list(comparison.reasons),
    )
```

Extend `ReconciliationReport` with a defaulted field:

```python
    restart_eligibility: RestartEligibilityResult | None = None
```

- [ ] **Step 4: Wire into `scripts/run_jforex_live.py`**

Update imports:

```python
    RestartEligibilityResult,
    derive_restart_eligibility,
```

Change `_reconcile_startup()` return type to:

```python
) -> tuple[
    RuntimeSessionMetadata,
    RuntimeSessionMetadata | None,
    RuntimeContextComparison,
    RestartEligibilityResult,
]:
```

After `comparison = compare_runtime_context(...)`, add:

```python
    restart_eligibility = derive_restart_eligibility(comparison)
```

When creating `ReconciliationReport`, pass:

```python
        restart_eligibility=restart_eligibility,
```

Return:

```python
    return current_metadata, persisted_metadata, comparison, restart_eligibility
```

In `main()`, replace:

```python
    current_metadata, _persisted_metadata, comparison = _reconcile_startup(cfg, paths)
```

with:

```python
    current_metadata, _persisted_metadata, comparison, restart_eligibility = _reconcile_startup(
        cfg,
        paths,
    )
```

Replace the incompatible check with:

```python
    if cfg.startup_mode == "resume" and not restart_eligibility.allow_new_entries:
        if restart_eligibility.eligibility.value == "RESTART_BLOCKED":
            _print_incompatible_restart_summary(cfg, paths, comparison)
            raise SystemExit(1)
        print(
            "[jforex-live] restart eligible in drain-only mode; new entries disabled",
            flush=True,
        )
```

The `RESTART_ELIGIBLE_DRAIN_ONLY` path must continue startup so existing exposure can be monitored and closed.

- [ ] **Step 5: Run targeted Python tests and verify pass**

Run:

```bash
uv run pytest -q tests/test_live_restart_reconciliation.py
```

Expected: all tests in `tests/test_live_restart_reconciliation.py` pass.

- [ ] **Step 6: Commit**

```bash
git add src/behemoth/live_restart/reconciliation.py scripts/run_jforex_live.py tests/test_live_restart_reconciliation.py
git commit -m "Add explicit live restart eligibility"
```

## Task 6: Java No-New-Entries Gate For Drain-Only Startup

**Files:**
- Modify: `scripts/run_jforex_live.py`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessCoordinatorTest.java`

- [ ] **Step 1: Write failing Java config test**

Append to `src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessCoordinatorTest.java`:

```java
    @Test
    void sessionConfigReadsNewEntriesEnabledFlag() {
        Map<String, String> environment = testEnvironment();
        environment.put("BEHEMOTH_JFOREX_NEW_ENTRIES_ENABLED", "false");

        JForexSessionConfig config = JForexSessionConfig.fromEnvironment(false, environment);

        assertThat(config.newEntriesEnabled()).isFalse();
    }
```

Add this test near the existing `JForexSessionConfig.fromEnvironment` tests at the top of `LiveReadinessCoordinatorTest`, where the private `testEnvironment()` helper is already in scope for all tests in the class.

- [ ] **Step 2: Write failing core behavior test**

Append to `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`:

```java
    @Test
    void executeActionsSkipsMarketOrderWhenNewEntriesGloballyDisabled() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"live","record_raw_ticks":true,"symbols":[]}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,
                            "bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,
                            "last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":289}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {
                              "predictions": [],
                              "actions": [{
                                "type":"OPEN_MARKET",
                                "symbol":"EURUSD",
                                "candidate_uid":"oco|EURUSD|100|h6|cand1",
                                "scan_id":"scan-drain-only",
                                "side":"BUY",
                                "reservation_id":"res-drain-only",
                                "broker_pos_id":null,
                                "horizon":6
                              }]
                            }
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-new-entries-disabled-test");
            JForexSessionConfig sessionConfig = new JForexSessionConfig(
                    server.url("/").uri(), URI.create("http://example.test/jnlp"),
                    "user", "pass", "", List.of("EURUSD"),
                    Instant.parse("2025-07-07T00:00:00Z"), Instant.parse("2025-07-09T00:00:00Z"),
                    tempDir, "run-1",
                    false, 10_000.0, 1, 900L, false, 60, false, "", 0,
                    false
            );
            PythonPredictionClient client = new PythonPredictionClient(
                    HttpClient.newHttpClient(), server.url("/").uri(),
                    Duration.ofSeconds(5), Duration.ofSeconds(5));
            ExecutionStateStore stateStore = new ExecutionStateStore(
                    tempDir.resolve("state.json"), client.objectMapper());
            RecordingExecutionPort recordingPort = new RecordingExecutionPort();
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig, client, stateStore,
                    new Stage14ArtifactWriter(tempDir, "test"),
                    JForexMetrics.start(sessionConfig), recordingPort);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));

            assertThat(recordingPort.marketOrders).isEmpty();
        }
    }
```

- [ ] **Step 3: Run Java tests and verify failure**

Run:

```bash
GRADLE_USER_HOME=/tmp/gradle-home gradle :jforex-adapter:test --tests com.behemoth.jforex.BehemothStrategyCoreTest --tests com.behemoth.jforex.live.LiveReadinessCoordinatorTest
```

Expected: compilation failure because `newEntriesEnabled` does not exist or constructor signature does not accept the final boolean.

- [ ] **Step 4: Add Java config field**

Modify `JForexSessionConfig` record to add:

```java
        boolean newEntriesEnabled,
```

Place it after `metricsPort` and before live-readiness fields.

Add this 20-argument convenience constructor below the existing 19-argument constructor, using the same parameter list plus `boolean newEntriesEnabled` after `int metricsPort`:

```java
    public JForexSessionConfig(
            URI apiBaseUri,
            URI jnlpUri,
            String username,
            String password,
            String accountId,
            List<String> instruments,
            Instant startUtc,
            Instant endUtc,
            Path reportDir,
            String runId,
            boolean riskEnabled,
            double requestedVolumeUnits,
            int tickBatchSize,
            long orderTtlSeconds,
            boolean nativeOcoEnabled,
            int apiTimeoutSeconds,
            boolean metricsEnabled,
            String metricsHost,
            int metricsPort,
            boolean newEntriesEnabled
    ) {
        this(
                apiBaseUri,
                jnlpUri,
                username,
                password,
                accountId,
                instruments,
                startUtc,
                endUtc,
                reportDir,
                runId,
                riskEnabled,
                requestedVolumeUnits,
                tickBatchSize,
                orderTtlSeconds,
                nativeOcoEnabled,
                apiTimeoutSeconds,
                metricsEnabled,
                metricsHost,
                metricsPort,
                newEntriesEnabled,
                DEFAULT_LIVE_READINESS_ENABLED,
                DEFAULT_LIVE_WARMUP_TICKS,
                DEFAULT_LIVE_LOOKBACK_DAYS,
                DEFAULT_LIVE_BRIDGE_WINDOW_MINUTES,
                DEFAULT_LIVE_FRESHNESS_SECONDS,
                DEFAULT_LIVE_STARTUP_BRIDGE_TIMEOUT_MINUTES
        );
    }
```

In the existing 19-argument constructor, replace the direct long `this(...)` call with a call to the new 20-argument constructor and pass:

```java
                true
```

as the final argument after `metricsPort`.

In `fromEnvironment()`, add after metrics port parsing:

```java
                Boolean.parseBoolean(setting(environment, "BEHEMOTH_JFOREX_NEW_ENTRIES_ENABLED", "true")),
```

The existing shorter constructor used by tests remains source-compatible because it supplies `newEntriesEnabled=true`.

- [ ] **Step 5: Add core gate**

In `BehemothStrategyCore.executeActions()`, replace:

```java
                if (!state.entriesAllowed) {
```

with:

```java
                if (!sessionConfig.newEntriesEnabled() || !state.entriesAllowed) {
```

Replace the detail string:

```java
                            "entries not allowed in current readiness state"
```

with:

```java
                            sessionConfig.newEntriesEnabled()
                                    ? "entries not allowed in current readiness state"
                                    : "new entries disabled by restart eligibility"
```

- [ ] **Step 6: Pass restart eligibility to JForex runner**

Modify `_start_live_runner()` in `scripts/run_jforex_live.py` to accept:

```python
def _start_live_runner(cfg: RunConfig, *, allow_new_entries: bool = True) -> subprocess.Popen[str]:
```

Add to the environment map:

```python
            "BEHEMOTH_JFOREX_NEW_ENTRIES_ENABLED": str(bool(allow_new_entries)).lower(),
```

In `main()`, replace:

```python
        java_proc = _start_live_runner(cfg)
```

with:

```python
        java_proc = _start_live_runner(
            cfg,
            allow_new_entries=restart_eligibility.allow_new_entries,
        )
```

- [ ] **Step 7: Run targeted Java tests and verify pass**

Run:

```bash
GRADLE_USER_HOME=/tmp/gradle-home gradle :jforex-adapter:test --tests com.behemoth.jforex.BehemothStrategyCoreTest --tests com.behemoth.jforex.live.LiveReadinessCoordinatorTest
```

Expected: both test classes pass.

- [ ] **Step 8: Run targeted Python live-runner import check**

Run:

```bash
uv run python -m py_compile scripts/run_jforex_live.py src/behemoth/live_restart/reconciliation.py
```

Expected: command exits 0.

- [ ] **Step 9: Commit**

```bash
git add scripts/run_jforex_live.py src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessCoordinatorTest.java
git commit -m "Disable new entries for drain-only restarts"
```

## Task 7: Make Target And End-To-End Verification

**Files:**
- Modify: `Makefile`
- Modify: `docs/superpowers/specs/2026-04-25-live-stage-commonality-dag-design.md`

- [ ] **Step 1: Add a Makefile target**

Add near live/promotion targets in `Makefile`:

```make
.PHONY: validate-live-stage-dag
validate-live-stage-dag:
	uv run python scripts/validate_live_stage_dag.py \
		--model-month $(or $(MODEL_MONTH),$(shell date -v-1m +%Y-%m 2>/dev/null || date -d "last month" +%Y-%m)) \
		--out-json $(or $(OUT_JSON),data/analysis/backtest_reconcile/live_stage_dag_validation.json)
```

- [ ] **Step 2: Update the approved spec status**

Modify the top of `docs/superpowers/specs/2026-04-25-live-stage-commonality-dag-design.md`:

```markdown
- **Status:** Approved; implementation plan written.
```

- [ ] **Step 3: Run Python targeted tests**

Run:

```bash
uv run pytest -q tests/test_ops_verdicts.py tests/test_stage_dag_contract.py tests/test_run_monthly_recert.py tests/test_run_promote_live.py tests/test_live_restart_reconciliation.py
```

Expected: all targeted Python tests pass.

- [ ] **Step 4: Run Java targeted tests**

Run:

```bash
GRADLE_USER_HOME=/tmp/gradle-home gradle :jforex-adapter:test --tests com.behemoth.jforex.BehemothStrategyCoreTest --tests com.behemoth.jforex.live.LiveReadinessCoordinatorTest
```

Expected: both Java test classes pass.

- [ ] **Step 5: Run formatting/build smoke checks**

Run:

```bash
git diff --check
uv run mkdocs build
```

Expected: `git diff --check` exits 0 and `mkdocs build` completes.

- [ ] **Step 6: Commit**

```bash
git add Makefile docs/superpowers/specs/2026-04-25-live-stage-commonality-dag-design.md
git commit -m "Document live stage DAG validation workflow"
```

## Final Verification Before PR

- [ ] Run the complete targeted verification set:

```bash
uv run pytest -q tests/test_ops_verdicts.py tests/test_stage_dag_contract.py tests/test_run_monthly_recert.py tests/test_run_promote_live.py tests/test_live_restart_reconciliation.py
GRADLE_USER_HOME=/tmp/gradle-home gradle :jforex-adapter:test --tests com.behemoth.jforex.BehemothStrategyCoreTest --tests com.behemoth.jforex.live.LiveReadinessCoordinatorTest
git diff --check
uv run mkdocs build
```

- [ ] Inspect commit list:

```bash
git log --oneline main..HEAD
```

Expected commits:

```text
Add shared operational verdict enums
Add live stage DAG contract validator
Record monthly recert DAG provenance
Require DAG provenance for live promotion
Add explicit live restart eligibility
Disable new entries for drain-only restarts
Document live stage DAG validation workflow
```

- [ ] Confirm only intended files changed:

```bash
git status --short
git diff --stat main..HEAD
```

Expected: clean status and changes limited to the files named in this plan.

## PR Notes

The PR description should state:

- Process `FAIL` and symbol `NO_GO` are now separate shared concepts.
- Monthly recert status records DAG provenance.
- Promotion refuses missing or wrong-branch DAG provenance.
- Restart eligibility maps clean resume, drain-only resume, and blocked restart explicitly.
- Drain-only restart disables new Java/JForex entries while still allowing the runtime to monitor and reconcile.
- Prefect is not introduced in this PR.

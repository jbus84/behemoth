# Stage 07 Logical And Statistical Audit

Stage ID: `stage07`

Runs logical, leakage, label-integrity, and execution-risk audits across the OCO research evidence.

## Canonical Commands

- `make audit-all`

## Required Inputs

- `data/analysis/tick_opportunity_mining/`
- `configs/research/governance/oco_rule_universe_registry.yaml`

## Produced Evidence

- `data/analysis/tick_opportunity_mining/oco_logical_audit_checks.csv`
- `data/analysis/tick_opportunity_mining/oco_leakage_integrity_checks.csv`
- `docs/analysis/oco_logical_audit_report.md`
- `docs/analysis/oco_leakage_integrity_report.md`
- `docs/analysis/oco_execution_risk_prelive_report.md`

## Gates

- `logical_audit_pass`: `PASS_FAIL`, severity `critical`

## Implementation Scope

- `Makefile` (registry)
- `scripts/audit_oco_execution_risk_prelive.py` (registry)
- `scripts/audit_oco_leakage_label_integrity.py` (registry)
- `scripts/audit_oco_pipeline_logical_issues.py` (registry)

## Tests

- `tests/test_oco_pipeline_logical_audit.py`
- `tests/test_oco_leakage_label_integrity.py`
- `tests/test_oco_execution_risk_prelive.py`

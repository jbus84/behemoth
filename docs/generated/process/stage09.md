# Stage 09 Live Governance And Deployment

Stage ID: `stage09`

Freezes Governance Locks, validates rule-universe coverage, and builds operator-facing Promotion evidence.

## Canonical Commands

- `make freeze-oco`

## Required Inputs

- `data/analysis/tick_opportunity_mining/reduced_core_rolling/`
- `models/oco/`
- `configs/research/governance/oco_rule_universe_registry.yaml`

## Produced Evidence

- `configs/research/governance/oco/${symbol}_oco_live_lock.json`
- `docs/strategy_bible/generated/stage_09_snapshot.md`
- `docs/analysis/operator_action_report.md`
- `docs/analysis/oco_alert_remediation_report.md`

## Gates

- `governance_lock_freeze_pass`: `PASS_FAIL`, severity `critical`
- `rule_universe_registry_pass`: `PASS_FAIL`, severity `critical`

## Implementation Scope

- `Makefile` (registry)
- `scripts/build_oco_governance_explainability_report.py` (registry)
- `scripts/build_operator_action_report.py` (registry)
- `scripts/freeze_oco_live_governance.py` (registry)
- `scripts/remediate_oco_monitoring_alerts.py` (registry)
- `scripts/validate_oco_rule_universe_registry.py` (registry)

## Tests

- `tests/test_oco_live_governance.py`
- `tests/test_validate_oco_rule_universe_registry.py`
- `tests/test_build_operator_action_report.py`

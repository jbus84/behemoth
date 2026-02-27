# OCO Governance Mapping

## Objective
Map informational diagnostics to potential future hard-gate promotion rules.

## Inputs
- `edge_clarity_stage_metrics.csv`
- Stage 7/9/10 governance and audit outputs.

## Process
- Assign each diagnostic to a governance class.
- Define promotion criteria from informational -> hard gate.

## Exact Calculations
Promotion score (policy-level):
- `promotion_ready = stable_3_cycles AND no_conflicting_high_issues AND threshold_defined`

## Causality / Leakage Controls
- Promotion cannot bypass existing causality checks (`L*`, logical audit, governance lock).

## Failure Modes
- Promoting unstable diagnostics creates false blockers.
- Not promoting persistent weak diagnostics increases latent risk.

## Interpretation Guide
- Stage 1-8 diagnostics: model/execution quality context.
- Stage 9-10 diagnostics: operational readiness context.

## Validation Gates
Candidate promotion map:
- `E11`, `E12`, `E13` -> Stage 4 execution hardening gates.
- `W13`, `W15` -> Stage 3 stability guardrails.
- `R02`, `R03` -> reduced-core concentration/stability gate candidates.
- `G01`, `G02` -> predeploy warning pressure controls.

## Reproduction Commands
```bash
uv run python scripts/validate_oco_docs_contract.py
```

## Traceability
- `docs/strategy_bible/stage_09_live_governance_and_deployment.md`
- `docs/strategy_bible/stage_10_known_risks_and_backlog.md`
- `docs/analysis/oco_edge_clarity_report.md`

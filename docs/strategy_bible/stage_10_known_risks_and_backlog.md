# Stage 10 - Known Risks And Backlog

## Objective
Track residual risk, open assumptions, and prioritized hardening tasks.

## Inputs
- Latest stage reports and audit issues.
- Deployment constraints and broker execution realities.

## Process
- Record unresolved risks that can affect realized performance.
- Classify by severity and controllability.
- Convert to concrete backlog tasks with acceptance tests.

## Risk Scoring Model (Operational)
Each risk is scored on two axes:
- impact: `1..4`
- likelihood: `1..4`

Score:
- `risk_score = impact * likelihood`

Severity bands:
- `1-3`: Low
- `4-7`: Medium
- `8-11`: High
- `12-16`: Critical

Status workflow:
- `open -> mitigated -> validated -> closed`
- status can only move to `closed` after acceptance tests pass on latest artifacts.

## Exact Calculations
- `risk_score = impact * likelihood`
- Severity bands:
- `1-3` low, `4-7` medium, `8-11` high, `12-16` critical
- Backlog diagnostics (informational):
- `B11_open_risks = count(status=open)`
- `B12_high_open = count(status=open and severity in {high,critical})`
- `B13_avg_days_open = mean(days_open)`

## Current Risk Register (Contract-Level)

| Risk ID | Description | Impact | Likelihood | Score | Current Status | Acceptance Test |
| --- | --- | --- | --- | --- | --- | --- |
| R10.1 | Governance lock drift between research and deploy config | 4 | 2 | 8 | Open | all checks in `validate_oco_live_governance.py` pass |
| R10.2 | Stop-limit overshoot regime shift reduces net expectancy | 3 | 3 | 9 | Open | Stage 4 cap/fill diagnostics stay within control limits |
| R10.3 | Reduced-core capacity degradation in new regimes | 3 | 2 | 6 | Open | Stage 5 monthly `rows`/`signal_rows` above configured floor |
| R10.4 | Robustness inference overconfidence from narrow test universe | 3 | 2 | 6 | Open | Stage 8 stress and LB gates remain passing |
| R10.5 | Audit cleanliness regression after upstream changes | 4 | 2 | 8 | Open | Stage 7 C01-C10 with zero critical/high failures |

## Pair Scope Constraint (Current Deployment)
- Active OCO production scope remains `EURUSD`, `GBPUSD`, and `USDJPY`.
- Pair scope governance is maintained by:
- `docs/analysis/oco_rule_universe_registry_report.md`
- Scope expansion requires a full Stage 1-10 replay and fresh governance lock artifacts.

## Outputs
- This page and linked issue artifacts.

## Causality / Leakage Controls
- Risk mitigation proposals must preserve existing anti-leakage contracts.

## Edge Hypothesis
- N/A; this stage prevents false confidence and untracked regression risk.

## Validation Gates
- No unresolved high-severity logical audit issues.
- Documented rationale for any accepted residual risk.

Promotion-to-close gates:
- risk has explicit owner and mitigation commit/artifact links
- acceptance test is automated or scripted and reproducible
- latest run evidence is attached
- no conflicting open issue in `oco_logical_audit_issues.csv`

Diagnostics-first backlog checks (informational, not blockers yet):
- `B11`: open risk count by symbol.
- `B12`: open high/critical risk count by symbol.
- `B13`: average risk age in days.

## Failure Modes
- Overfitting by silent parameter expansion.
- Cost model drift versus live ECN conditions.
- Capacity degradation from regime change.
- Untracked operational drift after governance freeze.

## Interpretation Guide
- High `risk_score` with increasing `days_open` should escalate priority even if no hard gate is failing.
- A clean Stage 7 does not eliminate operational backlog risk; monitor `B11-B13` trends.

## Operational Notes
- Revisit this page on every major strategy refresh.
- Minimum cadence: weekly while live, and always post-refresh.
- If any risk score rises to `>=12`, freeze new deploys until mitigated.

## Canonical Analysis Reports
- `docs/analysis/risk_checklist.md`
- `docs/analysis/oco_docs_contract_report.md`
- `docs/analysis/oco_rule_universe_registry_report.md`
- `docs/analysis/oco_alert_remediation_report.md`
- `docs/analysis/oco_governance_explainability_report.md`
- `docs/analysis/oco_leakage_integrity_report.md`
- `docs/analysis/taxonomy_rules.md`
- `docs/analysis/oco_stage_integrity_report.md`
- `docs/strategy_bible/operator_runbook.md`

## Operator Decision Tree
- If any hard gate in this stage fails, block promotion and escalate using the operator runbook.
- If only warning/amber diagnostics trigger, continue with mitigation and add an owner/deadline in remediation artifacts.

## How To Run
- Run the `Reproduction Commands` in this stage exactly as listed.
- Confirm artifacts are refreshed and timestamps are current before interpreting outcomes.

## How To Interpret Outputs
- Read `Key Results` first for pass/fail posture and core health metrics.
- Use `Interpretation Notes` and `Action Trigger Summary` to map observed values to operational actions.

## What To Do If It Fails
- `critical/high`: halt deployment progression, remediate root cause, rerun stage and downstream dependent stages.
- `medium/low`: open tracked remediation with owner and ETA, monitor for recurrence in next cycle.

## Reproduction Commands
```bash
uv run python scripts/audit_oco_pipeline_logical_issues.py
uv run python scripts/build_oco_strategy_bible.py \
  --manifest configs/research/docs/oco_bible_manifest.yaml --strict false
```

## Open Backlog (Current)

| Backlog ID | Item | Priority | Owner | Acceptance Test |
| --- | --- | --- | --- | --- |
| B10.7 | Add docs freshness escalation for stale evidence artifacts | Medium | Research lead | stale artifacts are flagged in runbook checklist and Stage 9 predeploy review |

## Recently Implemented Backlog (2026-02-27)

| Backlog ID | Item | Status | Evidence |
| --- | --- | --- | --- |
| B10.1 | Add docs CI check: all stages must contain generated snapshot and non-empty key table | Implemented | `make docs-contract`, `docs/analysis/oco_stage_integrity_report.md` |
| B10.2 | Add monthly drift report for overshoot/fill distributions by symbol | Implemented | `docs/analysis/oco_execution_drift_report.md` |
| B10.3 | Add explicit pre-registration note for reduced rule family universe | Implemented | `docs/strategy_bible/stage_02_opportunity_mining.md`, `docs/strategy_bible/stage_05_reduced_core.md`, `docs/analysis/oco_rule_universe_registry_report.md` |
| B10.4 | Add threshold lookback/retrain cadence sensitivity report | Implemented | `docs/analysis/oco_threshold_sensitivity_report.md` |
| B10.5 | Add escalation SLA enforcement for accepted exceptions older than 30 days | Implemented | `configs/research/governance/oco_monitoring_exceptions.yaml`, `docs/analysis/oco_alert_remediation_report.md`, `docs/analysis/oco_docs_contract_report.md` |
| B10.6 | Add alert remediation matrix with owner/action/expiry | Implemented | `docs/analysis/oco_alert_remediation_report.md`, `data/analysis/tick_opportunity_mining/oco_alert_disposition.csv` |

## Escalation Matrix
If any trigger occurs, required action is immediate:

| Trigger | Action |
| --- | --- |
| Stage 7 critical fail | block deploy, rerun impacted stages, re-audit |
| Stage 8 LB95 turns negative | freeze promotion, re-evaluate cost/stress assumptions |
| Stage 9 validation fail | rollback to last passing governance lock |
| Stage 4 overshoot p95 spike above control band | suspend affected symbol until cap review |

## Traceability
- `docs/strategy_bible/generated/audit_snapshot.md`
- `docs/analysis/risk_checklist.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_10:START -->
### Auto Snapshot - Stage 10

- generated_at: `2026-03-03 16:43:59 UTC`
- Risk backlog is derived from current logical-audit failures.
- When no failures exist, residual risks remain model/process assumptions rather than hard contract breaks.

#### Key Results
| status                 |   failed_checks |
|:-----------------------|----------------:|
| no_open_audit_failures |               0 |

#### Interpretation Notes
- Risk backlog is derived from current logical-audit failures.
- When no failures exist, residual risks remain model/process assumptions rather than hard contract breaks.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Details
| symbol   | severity_if_fail   |   total_checks |   failed_checks |
|:---------|:-------------------|---------------:|----------------:|
| EURUSD   | critical           |              3 |               0 |
| EURUSD   | high               |              5 |               0 |
| EURUSD   | medium             |              2 |               0 |
| GBPUSD   | critical           |              3 |               0 |
| GBPUSD   | high               |              5 |               0 |
| GBPUSD   | medium             |              2 |               0 |
| USDJPY   | critical           |              3 |               0 |
| USDJPY   | high               |              5 |               0 |
| USDJPY   | medium             |              2 |               0 |

#### Plots
![stage_10_risk_matrix](../figures/oco_bible/stage_10_risk_matrix.png)

- Risk SLA tracker exists but has no open rows. `source=data/analysis/tick_opportunity_mining/risk_sla_tracker.csv`
<!-- GENERATED:STAGE_10:END -->

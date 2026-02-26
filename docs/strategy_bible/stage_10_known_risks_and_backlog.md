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

## Current Risk Register (Contract-Level)

| Risk ID | Description | Impact | Likelihood | Score | Current Status | Acceptance Test |
| --- | --- | --- | --- | --- | --- | --- |
| R10.1 | Governance lock drift between research and deploy config | 4 | 2 | 8 | Open | all checks in `validate_oco_live_governance.py` pass |
| R10.2 | Stop-limit overshoot regime shift reduces net expectancy | 3 | 3 | 9 | Open | Stage 4 cap/fill diagnostics stay within control limits |
| R10.3 | Reduced-core capacity degradation in new regimes | 3 | 2 | 6 | Open | Stage 5 monthly `rows`/`signal_rows` above configured floor |
| R10.4 | Robustness inference overconfidence from narrow test universe | 3 | 2 | 6 | Open | Stage 8 stress and LB gates remain passing |
| R10.5 | Audit cleanliness regression after upstream changes | 4 | 2 | 8 | Open | Stage 7 C01-C10 with zero critical/high failures |

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

## Failure Modes
- Overfitting by silent parameter expansion.
- Cost model drift versus live ECN conditions.
- Capacity degradation from regime change.
- Untracked operational drift after governance freeze.

## Operational Notes
- Revisit this page on every major strategy refresh.
- Minimum cadence: weekly while live, and always post-refresh.
- If any risk score rises to `>=12`, freeze new deploys until mitigated.

## Open Backlog (Current)

| Backlog ID | Item | Priority | Owner | Acceptance Test |
| --- | --- | --- | --- | --- |
| B10.1 | Add docs CI check: all stages must contain generated snapshot and non-empty key table | High | Research infra | CI fails when any stage snapshot marker missing |
| B10.2 | Add monthly drift report for overshoot/fill distributions by symbol | High | Execution research | Stage 4 drift report emitted with p50/p95 change bands |
| B10.3 | Add explicit pre-registration note for reduced rule family universe | Medium | Research lead | Stage 2/5 docs include versioned rule-universe rationale |
| B10.4 | Add threshold lookback/retrain cadence sensitivity report | Medium | WFO research | Stage 3/9 sensitivity table committed per release |

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
- `docs/analysis/stable_pairs_whitelist.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_10:START -->
### Auto Snapshot - Stage 10

- generated_at: `2026-02-26 22:19:06 UTC`
- Risk backlog is derived from current logical-audit failures.
- When no failures exist, residual risks remain model/process assumptions rather than hard contract breaks.

#### Key Results
| status                 |   failed_checks |
|:-----------------------|----------------:|
| no_open_audit_failures |               0 |

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

- Risk SLA tracker exists but has no open rows. `source=/Users/danielfisher/repositories/behemoth/data/analysis/tick_opportunity_mining/risk_sla_tracker.csv`
<!-- GENERATED:STAGE_10:END -->

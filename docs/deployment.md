# Deployment

## Current State
The current OCO system is operated as a governed research pipeline. Live execution deployment is optional and must follow Stage 9 governance locks.

Generated deployment summary tables below are supportive evidence, not standalone authority. If the rolling summary block is sparse, stale, or unavailable in a local docs rebuild, use the operator runbook, generated stage snapshots, and docs-contract outputs for deployment decisions.

## Authority Note
- Authority label: `canonical`
- Authoritative for: deployment posture, promotion checklist, and the boundary between active governance and optional live runtime integration.
- Not authoritative for: current symbol readiness or gate-pass truth when generated stage snapshots or docs-contract outputs disagree.
- Depends on: [`docs/strategy_bible/operator_runbook.md`](./strategy_bible/operator_runbook.md), [`docs/strategy_bible/generated/pipeline_snapshot.md`](./strategy_bible/generated/pipeline_snapshot.md), [`docs/strategy_bible/generated/stage_09_snapshot.md`](./strategy_bible/generated/stage_09_snapshot.md), and [`docs/analysis/oco_docs_contract_report.md`](./analysis/oco_docs_contract_report.md).

## Promotion Checklist
1. Stage 1-11 snapshots refreshed.
2. `make docs-contract-ci` passes with zero failed checks.
3. alert dispositions and explainability are current.
4. governance lock validation passes for target symbols.
5. docs site rebuild passes.

## Live Runtime Integration (When Enabled)
If enabling the live runtime through the API/broker bridge:
- enforce stop-limit contract from Stage 4,
- enforce state/threshold lock from Stage 9,
- persist execution evidence required by remediation and monitoring.

## Legacy Docker/API Stack
Compose/API deployment docs remain a `compatibility` surface for optional live runtime services and are not required for core OCO research governance.

## Rolling Historical Evidence

<!-- GENERATED:SYSREF:DEPLOYMENT:START -->
- generated_at_utc: `2026-04-12T17:21:17Z`
- symbols_covered: `EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD`
- stop-limit_reference: `stage_04_execution_realism`
- artifact_sources:
  - `data/analysis/tick_opportunity_mining/oco_execution_drift_monthly.csv`
  - `data/analysis/tick_opportunity_mining/oco_threshold_sensitivity.csv`
  - `data/analysis/tick_opportunity_mining/operator_action_status.csv`
  - `data/analysis/tick_opportunity_mining/oco_alert_disposition.csv`
  - `data/analysis/tick_opportunity_mining/docs_contract_checks.csv`

#### Rolling Snapshot By Symbol
| symbol   | latest_month   |   drift_fill_rate |   drift_overshoot_p95 |   w13_fragility |   policy_quantile | mc_s1_lb95   | reduced_mean_gross   |   non_green_actions |   non_green_alerts | ftmo_block_rate   | ftmo_budget_exceeded_rate   |   ftmo_stale_pending_count | ftmo_reconciliation_pass   |
|:---------|:---------------|------------------:|----------------------:|----------------:|------------------:|:-------------|:---------------------|--------------------:|-------------------:|:------------------|:----------------------------|---------------------------:|:---------------------------|
| EURUSD   | 2026-03        |            0.989  |                   0.4 |          1.8213 |               0.9 |              |                      |                   3 |                  2 |                   |                             |                          0 |                            |
| GBPUSD   | 2026-03        |            0.9823 |                   0.4 |          2.1161 |               0.9 |              |                      |                   2 |                 13 |                   |                             |                          0 |                            |
| USDJPY   | 2026-03        |            0.9802 |                   0.6 |          3.066  |               0.9 |              |                      |                   1 |                  6 |                   |                             |                          0 |                            |
| USDCHF   | 2026-03        |            0.9901 |                   0.3 |          1.5943 |               0.9 |              |                      |                   3 |                 10 |                   |                             |                          0 |                            |
| AUDUSD   | 2026-03        |            0.9882 |                   0.4 |          1.4818 |               0.9 |              |                      |                   1 |                  6 |                   |                             |                          0 |                            |
| USDCAD   | 2026-03        |            0.9944 |                   0.3 |          1.5148 |               0.9 |              |                      |                   2 |                  3 |                   |                             |                          0 |                            |

#### Rolling Trend (Last 3 Months)
| symbol   |   months_used |   fill_rate_mean_3m |   overshoot_p95_mean_3m |
|:---------|--------------:|--------------------:|------------------------:|
| EURUSD   |             3 |              0.9881 |                  0.3333 |
| GBPUSD   |             3 |              0.9875 |                  0.4    |
| USDJPY   |             3 |              0.9761 |                  0.7    |
| USDCHF   |             3 |              0.9895 |                  0.3    |
| AUDUSD   |             3 |              0.989  |                  0.3333 |
| USDCAD   |             3 |              0.9871 |                  0.3333 |

#### Governance Snapshot
|   checks_failed |   high_critical_failed |   max_age_hours_c6 |   run_delta_metric_rows_changed |   run_delta_gate_rows_changed |
|----------------:|-----------------------:|-------------------:|--------------------------------:|------------------------------:|
|              11 |                     10 |           0.000418 |                               0 |                             0 |
<!-- GENERATED:SYSREF:DEPLOYMENT:END -->

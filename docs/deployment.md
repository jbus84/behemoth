# Deployment

## Current State
The current OCO system is operated as a governed research pipeline. Live execution deployment is optional and must follow Stage 9 governance locks.

Generated deployment summary tables below are supportive evidence, not standalone authority. If the rolling summary block is sparse, stale, or unavailable in a local docs rebuild, use the operator runbook, generated stage snapshots, and docs-contract outputs as the decision surface.

## Authority Note
- Authority label: `canonical`
- Authoritative for: deployment posture, promotion checklist, and the boundary between active governance and optional runtime integration.
- Not authoritative for: current symbol readiness or gate-pass truth when generated stage snapshots or docs-contract outputs disagree.
- Depends on: [`docs/strategy_bible/operator_runbook.md`](./strategy_bible/operator_runbook.md), [`docs/strategy_bible/generated/pipeline_snapshot.md`](./strategy_bible/generated/pipeline_snapshot.md), [`docs/strategy_bible/generated/stage_09_snapshot.md`](./strategy_bible/generated/stage_09_snapshot.md), and [`docs/analysis/oco_docs_contract_report.md`](./analysis/oco_docs_contract_report.md).

## Promotion Checklist
1. Stage 1-11 snapshots refreshed.
2. `make docs-contract-ci` passes with zero failed checks.
3. alert dispositions and explainability are current.
4. governance lock validation passes for target symbols.
5. docs site rebuild passes.

## Execution Integration (When Enabled)
If deploying through API/broker bridge:
- enforce stop-limit contract from Stage 4,
- enforce state/threshold lock from Stage 9,
- persist execution evidence required by remediation and monitoring.

## Legacy Docker/API Stack
Compose/API deployment docs remain a `compatibility` surface for optional runtime services and are not required for core OCO research governance.

## Rolling Historical Evidence

<!-- GENERATED:SYSREF:DEPLOYMENT:START -->
- generated_at_utc: `2026-03-23T20:07:53Z`
- symbols_covered: `EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD`
- stop-limit_reference: `stage_04_execution_realism`
- artifact_sources:
  - `data/analysis/tick_opportunity_mining/oco_execution_drift_monthly.csv`
  - `data/analysis/tick_opportunity_mining/oco_threshold_sensitivity.csv`
  - `data/analysis/tick_opportunity_mining/operator_action_status.csv`
  - `data/analysis/tick_opportunity_mining/oco_alert_disposition.csv`
  - `data/analysis/tick_opportunity_mining/ftmo_allocator_monitoring_metrics.csv`
  - `data/analysis/tick_opportunity_mining/ftmo_reservation_reconciliation.csv`
  - `data/analysis/tick_opportunity_mining/execution_mc_symbol_scenarios.csv`
  - `data/analysis/tick_opportunity_mining/docs_contract_checks.csv`
  - `data/analysis/tick_opportunity_mining/run_delta_summary.csv`

#### Rolling Snapshot By Symbol
| symbol   | latest_month   |   drift_fill_rate |   drift_overshoot_p95 |   w13_fragility |   policy_quantile |   mc_s1_lb95 | reduced_mean_gross   |   non_green_actions |   non_green_alerts |   ftmo_block_rate |   ftmo_budget_exceeded_rate |   ftmo_stale_pending_count | ftmo_reconciliation_pass   |
|:---------|:---------------|------------------:|----------------------:|----------------:|------------------:|-------------:|:---------------------|--------------------:|-------------------:|------------------:|----------------------------:|---------------------------:|:---------------------------|
| EURUSD   | 2026-02        |            0.0513 |                47.395 |          0.5039 |               0.9 |       1.18   |                      |                   7 |                 16 |               0.4 |                         0.2 |                          0 | false                      |
| GBPUSD   | 2026-02        |            0.0278 |                64.2   |          0.4116 |               0.9 |       0.8109 |                      |                   1 |                 14 |               0   |                         0   |                          0 | true                       |
| USDJPY   | 2026-02        |            0.0283 |                88.9   |          0.5923 |               0.9 |       1.0729 |                      |                   1 |                 15 |               0   |                         0   |                          0 | true                       |
| USDCHF   | 2026-02        |            0.0454 |                44.7   |          0.3023 |               0.9 |       0.7029 |                      |                   1 |                 15 |               0   |                         0   |                          0 | true                       |
| AUDUSD   | 2026-02        |            0.0432 |                39     |          0.2601 |               0.9 |       0.4893 |                      |                   2 |                 12 |               0   |                         0   |                          0 | true                       |
| USDCAD   | 2026-02        |            0.0604 |                69.6   |          0.4037 |               0.9 |       0.5715 |                      |                   2 |                 13 |               0   |                         0   |                          0 | true                       |

#### Rolling Trend (Last 3 Months)
| symbol   |   months_used |   fill_rate_mean_3m |   overshoot_p95_mean_3m |
|:---------|--------------:|--------------------:|------------------------:|
| EURUSD   |             3 |              0.3567 |                 46.8317 |
| GBPUSD   |             3 |              0.3438 |                 47.1333 |
| USDJPY   |             3 |              0.3476 |                 57.5783 |
| USDCHF   |             3 |              0.3388 |                 40.9667 |
| AUDUSD   |             3 |              0.3494 |                 30.6867 |
| USDCAD   |             3 |              0.3555 |                 35.9    |

#### Governance Snapshot
|   checks_failed |   high_critical_failed |   max_age_hours_c6 |   run_delta_metric_rows_changed |   run_delta_gate_rows_changed |
|----------------:|-----------------------:|-------------------:|--------------------------------:|------------------------------:|
|               2 |                      1 |           0.001635 |                              12 |                             0 |
<!-- GENERATED:SYSREF:DEPLOYMENT:END -->

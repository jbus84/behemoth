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
- generated_at_utc: `2026-03-10T10:13:43Z`
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
| symbol   | latest_month   | drift_fill_rate   | drift_overshoot_p95   | w13_fragility   | policy_quantile   | mc_s1_lb95   | reduced_mean_gross   |   non_green_actions |   non_green_alerts | ftmo_block_rate   | ftmo_budget_exceeded_rate   |   ftmo_stale_pending_count | ftmo_reconciliation_pass   |
|:---------|:---------------|:------------------|:----------------------|:----------------|:------------------|:-------------|:---------------------|--------------------:|-------------------:|:------------------|:----------------------------|---------------------------:|:---------------------------|
| EURUSD   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |                   |                             |                          0 |                            |
| GBPUSD   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |                   |                             |                          0 |                            |
| USDJPY   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |                   |                             |                          0 |                            |
| USDCHF   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |                   |                             |                          0 |                            |
| AUDUSD   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |                   |                             |                          0 |                            |
| USDCAD   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |                   |                             |                          0 |                            |

#### Rolling Trend (Last 3 Months)
| symbol   |   months_used | fill_rate_mean_3m   | overshoot_p95_mean_3m   |
|:---------|--------------:|:--------------------|:------------------------|
| EURUSD   |             0 |                     |                         |
| GBPUSD   |             0 |                     |                         |
| USDJPY   |             0 |                     |                         |
| USDCHF   |             0 |                     |                         |
| AUDUSD   |             0 |                     |                         |
| USDCAD   |             0 |                     |                         |

#### Governance Snapshot
|   checks_failed |   high_critical_failed | max_age_hours_c6   |   run_delta_metric_rows_changed |   run_delta_gate_rows_changed |
|----------------:|-----------------------:|:-------------------|--------------------------------:|------------------------------:|
|               0 |                      0 |                    |                               0 |                             0 |
<!-- GENERATED:SYSREF:DEPLOYMENT:END -->

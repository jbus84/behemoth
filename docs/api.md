# API

## Status
The OCO strategy pipeline does not require a running API for core research, validation, or governance.

## What Is Required Today
- Stage pipeline execution via scripts.
- Artifact and docs contracts via `make docs-contract-ci`.
- Governance lock validation via Stage 9 artifacts.

## Optional Execution Interface (Future)
If an execution service is used, it must implement the same contract as the strategy docs:
- consume only approved states from governance lock,
- place stop-limit style entries,
- return tick-realized touch/fill outcomes,
- persist auditable execution evidence.

Minimum payload contract should include:
- `symbol`, `event_ts`, `side`, `barrier_pips`, `horizon`, `cap_pips`, `state_id`, `candidate_uid`.

## Legacy API Stack
Legacy FastAPI components have been removed and are no longer the source of truth for the current OCO research process.

## Rolling Historical Evidence

<!-- GENERATED:SYSREF:API:START -->
- generated_at_utc: `2026-03-30T10:11:24Z`
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
| EURUSD   | 2026-02        |            0.0496 |                 46.8  |          0.5039 |               0.9 |       1.18   |                      |                   6 |                 17 |               0.4 |                         0.2 |                          0 | false                      |
| GBPUSD   | 2026-02        |            0.0298 |                 64.3  |          0.4116 |               0.9 |       0.8109 |                      |                   2 |                 15 |               0   |                         0   |                          0 | true                       |
| USDJPY   | 2026-02        |            0.0286 |                 89.8  |          0.5923 |               0.9 |       1.0729 |                      |                   1 |                 15 |               0   |                         0   |                          0 | true                       |
| USDCHF   | 2026-02        |            0.0476 |                 42.8  |          0.3023 |               0.9 |       0.7029 |                      |                   2 |                 15 |               0   |                         0   |                          0 | true                       |
| AUDUSD   | 2026-02        |            0.0467 |                 38.4  |          0.2601 |               0.9 |       0.4893 |                      |                   2 |                 12 |               0   |                         0   |                          0 | true                       |
| USDCAD   | 2026-02        |            0.0551 |                 70.82 |          0.4037 |               0.9 |       0.5715 |                      |                   2 |                 16 |               0   |                         0   |                          0 | true                       |

#### Rolling Trend (Last 3 Months)
| symbol   |   months_used |   fill_rate_mean_3m |   overshoot_p95_mean_3m |
|:---------|--------------:|--------------------:|------------------------:|
| EURUSD   |             3 |              0.3562 |                 46.1667 |
| GBPUSD   |             3 |              0.3451 |                 47.0333 |
| USDJPY   |             3 |              0.3479 |                 58.7333 |
| USDCHF   |             3 |              0.3394 |                 40.1667 |
| AUDUSD   |             3 |              0.3502 |                 30.89   |
| USDCAD   |             3 |              0.3556 |                 37.5067 |

#### Governance Snapshot
|   checks_failed |   high_critical_failed |   max_age_hours_c6 |   run_delta_metric_rows_changed |   run_delta_gate_rows_changed |
|----------------:|-----------------------:|-------------------:|--------------------------------:|------------------------------:|
|               2 |                      1 |           0.000569 |                              12 |                             0 |
<!-- GENERATED:SYSREF:API:END -->

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
<!-- GENERATED:SYSREF:API:END -->

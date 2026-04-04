# Persistence Schema

## Current OCO Persistence Model
The active pipeline stores state in versioned artifacts (CSV/Parquet/Markdown), not a mandatory relational DB.

## Canonical Artifact Groups
| Group | Path Pattern | Purpose |
| --- | --- | --- |
| Stage metrics | `data/analysis/tick_opportunity_mining/*` | machine-readable governance and analysis outputs |
| Analysis reports | `docs/analysis/*.md` | human-readable evidence |
| Stage specs/snapshots | `docs/strategy_bible/*.md`, `docs/strategy_bible/generated/*.md` | process contract and latest run state |
| Governance configs | `configs/research/governance/*` | locked policy inputs |

## Optional Legacy SQL Schema
Persistence is fully handled by rolling pipeline artifacts. No relational schema is required for core OCO research governance.

## Rolling Historical Evidence

<!-- GENERATED:SYSREF:DB_SCHEMA:START -->
- generated_at_utc: `2026-04-03T12:49:44Z`
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
| EURUSD   | 2026-02        |            0.8892 |                   1.2 |          0.4424 |               0.9 |       1.18   |                      |                   6 |                 17 |               0.4 |                         0.2 |                          0 | false                      |
| GBPUSD   | 2026-02        |            0.9954 |                   0.5 |          0.4189 |               0.9 |       0.8109 |                      |                   2 |                  1 |               0   |                         0   |                          0 | true                       |
| USDJPY   | 2026-02        |            0.9794 |                   0.7 |          0.6499 |               0.9 |       1.0729 |                      |                   1 |                  0 |               0   |                         0   |                          0 | true                       |
| USDCHF   | 2026-02        |            0.9667 |                   0.4 |          0.2857 |               0.9 |       0.7029 |                      |                   2 |                  7 |               0   |                         0   |                          0 | true                       |
| AUDUSD   | 2026-02        |            0.982  |                   0.3 |          0.2364 |               0.9 |       0.4893 |                      |                   2 |                  3 |               0   |                         0   |                          0 | true                       |
| USDCAD   | 2026-02        |            0.9698 |                   0.5 |          0.395  |               0.9 |       0.5715 |                      |                   2 |                  4 |               0   |                         0   |                          0 | true                       |

#### Rolling Trend (Last 3 Months)
| symbol   |   months_used |   fill_rate_mean_3m |   overshoot_p95_mean_3m |
|:---------|--------------:|--------------------:|------------------------:|
| EURUSD   |             3 |              0.9316 |                  0.8    |
| GBPUSD   |             3 |              0.9907 |                  0.4667 |
| USDJPY   |             3 |              0.9796 |                  0.7    |
| USDCHF   |             3 |              0.972  |                  0.4667 |
| AUDUSD   |             3 |              0.9777 |                  0.3333 |
| USDCAD   |             3 |              0.9704 |                  0.4667 |

#### Governance Snapshot
|   checks_failed |   high_critical_failed |   max_age_hours_c6 |   run_delta_metric_rows_changed |   run_delta_gate_rows_changed |
|----------------:|-----------------------:|-------------------:|--------------------------------:|------------------------------:|
|               2 |                      1 |           0.000679 |                              12 |                             0 |
<!-- GENERATED:SYSREF:DB_SCHEMA:END -->

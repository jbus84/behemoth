# Data Pipeline

## Current Pipeline (Authoritative)

```mermaid
flowchart LR
  A[Raw ticks] --> B[Tick velocity bars]
  B --> C[OCO candidate mining]
  C --> D[Monthly WFO scoring]
  D --> E[Stop-limit tick realism]
  E --> F[Reduced core selection]
  F --> G[Tick-exact verification]
  G --> H[Robustness + stress]
  H --> I[Governance lock + remediation]
  I --> J[Strategy bible + docs contracts]
```

## Key Inputs
- Tick source root (runtime configured path).
- Velocity bars: `data/analysis/tick_velocity/*_tick_velocity.parquet`.
- Stage configs: `configs/research/experiments/*.yaml`.

## Key Outputs
- Analysis artifacts: `data/analysis/tick_opportunity_mining/*`.
- Human-readable reports: `docs/analysis/*.md`.
- Stage references: `docs/strategy_bible/*.md` and generated snapshots.

## Causality Contract
- monthly WFO ordering is strict (train before test),
- rolling thresholds are causal,
- execution realism uses tick-first touch reconstruction without forward leakage.

## Rolling Historical Evidence

<!-- GENERATED:SYSREF:DATA_PIPELINE:START -->
- generated_at_utc: `2026-02-27T18:39:10Z`
- symbols_covered: `EURUSD,GBPUSD,USDJPY`
- stop-limit_reference: `stage_04_execution_realism`
- artifact_sources:
  - `data/analysis/tick_opportunity_mining/oco_execution_drift_monthly.csv`
  - `data/analysis/tick_opportunity_mining/oco_threshold_sensitivity.csv`
  - `data/analysis/tick_opportunity_mining/operator_action_status.csv`
  - `data/analysis/tick_opportunity_mining/oco_alert_disposition.csv`
  - `data/analysis/tick_opportunity_mining/execution_mc_symbol_scenarios.csv`
  - `data/analysis/tick_opportunity_mining/docs_contract_checks.csv`
  - `data/analysis/tick_opportunity_mining/run_delta_summary.csv`

#### Rolling Snapshot By Symbol
| symbol   | latest_month   | drift_fill_rate   | drift_overshoot_p95   | w13_fragility   | policy_quantile   | mc_s1_lb95   | reduced_mean_gross   |   non_green_actions |   non_green_alerts |
|:---------|:---------------|:------------------|:----------------------|:----------------|:------------------|:-------------|:---------------------|--------------------:|-------------------:|
| EURUSD   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |
| GBPUSD   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |
| USDJPY   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |

#### Rolling Trend (Last 3 Months)
| symbol   |   months_used | fill_rate_mean_3m   | overshoot_p95_mean_3m   |
|:---------|--------------:|:--------------------|:------------------------|
| EURUSD   |             0 |                     |                         |
| GBPUSD   |             0 |                     |                         |
| USDJPY   |             0 |                     |                         |

#### Governance Snapshot
|   checks_failed |   high_critical_failed | max_age_hours_c6   |   run_delta_metric_rows_changed |   run_delta_gate_rows_changed |
|----------------:|-----------------------:|:-------------------|--------------------------------:|------------------------------:|
|               0 |                      0 |                    |                               0 |                             0 |
<!-- GENERATED:SYSREF:DATA_PIPELINE:END -->

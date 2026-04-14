# Architecture

This repository currently runs as a research-first OCO pipeline, not an always-on API service.

## Current Runtime Model

```mermaid
flowchart TD
  A[Raw tick data] --> B[Stage 1: data foundation]
  B --> C[Stage 2: opportunity mining]
  C --> D[Stage 3: monthly WFO]
  D --> E[Stage 4: stop-limit realism]
  E --> F[Stage 5: reduced core]
  F --> G[Stage 6: tick-exact checks]
  G --> H[Stage 7: logical/statistical audit]
  H --> I[Stage 8: robustness and stress]
  I --> J[Stage 9: governance lock + remediation]
  J --> K[Stage 10: risk backlog]
  K --> L[Stage 11: execution Monte Carlo]
```

## Source of Truth
- Process and controls: `docs/strategy_bible/`
- Generated stage evidence: `docs/strategy_bible/generated/`
- Analysis reports: `docs/analysis/`
- Contract checks: `data/analysis/tick_opportunity_mining/docs_contract_checks.csv`

## Architecture Boundary
- Mandatory: offline/research pipeline and governance artifacts.
- Outputs: Live execution locks and allowed state matrices.
- Current production research scope: `EURUSD`, `GBPUSD`, `USDJPY`.

## Next Integration Step
When execution integration is enabled, treat it as a thin adapter over the Stage 9 lock and Stage 4 stop-limit contract, not as a separate strategy engine.

## Rolling Historical Evidence

<!-- GENERATED:SYSREF:ARCHITECTURE:START -->
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
<!-- GENERATED:SYSREF:ARCHITECTURE:END -->

# Risk Controls

Risk is controlled through stage gates, not a single runtime kill-switch.

## Active Control Layers
| Layer | Purpose | Primary Artifacts |
| --- | --- | --- |
| Stage 4 execution realism | stop-limit fill quality and overshoot control | `oco_execution_drift_report.md`, Stage 4 snapshot |
| Stage 7 audit | logical/statistical hygiene | `oco_logical_audit_report.md` |
| Stage 8 robustness | stress and conservative bounds | `oco_edge_clarity_report.md` |
| Stage 9 governance | lock drift + alert remediation | `operator_action_report.md`, `oco_alert_remediation_report.md` |
| Stage 10 backlog | residual risk ownership and SLA | Stage 10 spec + snapshot |
| Stage 11 MC | execution stress scenarios | `oco_execution_monte_carlo_report.md` |

## Hard Block Conditions
- docs-contract high/critical failures,
- governance lock drift,
- failed stage integrity checks,
- unresolved red policy actions.

## Current Risk Posture
Strategy decisions must be based on refreshed artifacts (freshness SLA in Stage 9/operator runbook), not stale historical summaries.

## Rolling Historical Evidence

<!-- GENERATED:SYSREF:RISK_CONTROLS:START -->
- generated_at_utc: `2026-03-04T19:25:30Z`
- symbols_covered: `EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD`
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
| USDCHF   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |
| AUDUSD   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |
| USDCAD   |                |                   |                       |                 |                   |              |                      |                   0 |                  0 |

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
<!-- GENERATED:SYSREF:RISK_CONTROLS:END -->

# API Reference

## Scope
This page refers to optional legacy API modules under `services/api/`.

## Current Recommendation
For current OCO strategy work, use these as implementation references only. The authoritative behavior contracts are documented in:
- `docs/strategy_bible/stage_04_execution_realism.md`
- `docs/strategy_bible/stage_09_live_governance_and_deployment.md`
- `docs/strategy_bible/operator_runbook.md`

## Legacy Module Map
- `services.api.main`
- `services.api.models`
- `services.api.schemas`
- `services.api.risk`
- `services.api.guardrail`
- `services.api.settings`
- `services.api.validation`
- `services.api.predict`
- `services.api.weights`
- `services.api.cache`
- `services.api.state`

## Rolling Historical Evidence

<!-- GENERATED:SYSREF:API_REFERENCE:START -->
- generated_at_utc: `2026-02-27T16:58:52Z`
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
<!-- GENERATED:SYSREF:API_REFERENCE:END -->

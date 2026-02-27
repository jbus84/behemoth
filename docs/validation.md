# Validation

## Validation Layers
1. Stage integrity and required section checks.
2. Rule-universe registry lock checks.
3. Alert disposition and governance explainability checks.
4. Docs contract checks (including freshness, metadata, and path portability).
5. Strategy-level robustness and Monte Carlo checks.

## Core Commands
```bash
make docs-contract-ci
uv run pytest -q tests/test_oco_docs_contract.py tests/test_stage_integrity_gate.py
uv run mkdocs build
```

## Primary Evidence
- `data/analysis/tick_opportunity_mining/docs_contract_checks.csv`
- `data/analysis/tick_opportunity_mining/oco_stage_integrity_checks.csv`
- `docs/analysis/oco_docs_contract_report.md`

## Rolling Historical Evidence

<!-- GENERATED:SYSREF:VALIDATION:START -->
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
<!-- GENERATED:SYSREF:VALIDATION:END -->

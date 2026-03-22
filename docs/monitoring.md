# Monitoring

## Primary Monitoring Mode (Current)
Monitoring is artifact-driven from each run:
- `docs/analysis/operator_action_report.md`
- `docs/analysis/oco_alert_remediation_report.md`
- `docs/analysis/oco_governance_explainability_report.md`
- `docs/analysis/oco_docs_contract_report.md`

## Required Daily/Weekly Signals
- execution drift metrics (`E_DRIFT_*`),
- threshold sensitivity alerts (`TS*`),
- governance near-fail/lock-drift diagnostics (`G01`, `G03`),
- freshness and exception expiry.

## Infra Monitoring
Prometheus/Grafana remains optional for research-only runs, but it is the active observability path for the Python API during Stage 13 Dukascopy TestClient validation and for the JForex adapter during Stage 14 tester/demo validation.

Current runtime scrape targets:
- Python API: `http://127.0.0.1:8001/metrics`
- JForex adapter: `http://127.0.0.1:9464/metrics`

Grafana dashboards are provisioned from `provisioning/dashboards/` and Prometheus scrapes both targets via `docker-compose.yml` + `prometheus.yml`.

## Dukascopy Demo Certification
For the demo certification run, bring up the monitoring stack with `make observability-up`, then print the operator links with `make demo-cert-monitor`.

The provisioned JForex dashboard is `behemoth-jforex-runtime` in Grafana at `http://127.0.0.1:3000/d/behemoth-jforex-runtime/behemoth-jforex-runtime?orgId=1`.

Use the runtime readiness snapshot at `data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json` for direct evidence.

The key certification signals are:
- symbol readiness state (`READY`, `STALE_PAUSED`, `ERROR_PAUSED`)
- entries-allowed status by symbol
- tick staleness in seconds
- predict calls and predict failures by symbol

## Rolling Historical Evidence

<!-- GENERATED:SYSREF:MONITORING:START -->
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
<!-- GENERATED:SYSREF:MONITORING:END -->

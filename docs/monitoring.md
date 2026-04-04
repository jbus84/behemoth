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
For the demo certification run, start the monitoring stack and print the operator links with `make demo-cert-monitor`.

The provisioned JForex dashboard is `behemoth-jforex-runtime` in Grafana at `http://127.0.0.1:3000/d/behemoth-jforex-runtime/behemoth-jforex-runtime?orgId=1`.

Use the runtime readiness snapshot at `data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json` for direct evidence.

The key certification signals are:
- symbol readiness state (`READY`, `STALE_PAUSED`, `ERROR_PAUSED`)
- entries-allowed status by symbol
- tick staleness in seconds
- predict calls and predict failures by symbol

The readiness panel uses the Java enum ordinals with explicit mapping:
- `0=COLD`
- `1=PARQUET_WARMING`
- `2=BRIDGING`
- `3=READY`
- `4=STALE_PAUSED`
- `5=ERROR_PAUSED`

## Rolling Historical Evidence

<!-- GENERATED:SYSREF:MONITORING:START -->
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
<!-- GENERATED:SYSREF:MONITORING:END -->

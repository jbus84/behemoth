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

## Build Commands (Raw Ticks -> Velocity)
```bash
uv run python scripts/build_global_tick_bars.py \
  --tick-root /Users/danielfisher/Desktop/dukascopy_ticks \
  --output-dir data/global_tickbars \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF \
  --base-ticks 100 \
  --aggregate-multiples 1,10,20 \
  --price-source bid \
  --timestamp-mode utc_naive

uv run python scripts/build_tick_velocity_dataset.py \
  --tick-root /Users/danielfisher/Desktop/dukascopy_ticks \
  --tickbar-dir data/global_tickbars \
  --out-dir data/analysis/tick_velocity \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF \
  --bar-ticks-grid 100,1000,2000 \
  --vel-horizons 1,2,5,10 \
  --target-horizons 1,2,3 \
  --vol-window 96 \
  --cost-window 288 \
  --timestamp-mode utc_naive \
  --overwrite
```

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
<!-- GENERATED:SYSREF:DATA_PIPELINE:END -->

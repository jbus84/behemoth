# Stage 1 - Data Foundation

## Objective
Define and verify the minimum data-quality contract required for causal OCO research and deployment decisions.

## Inputs
- Raw ticks root (runtime):
- `/Users/danielfisher/Desktop/tick/<SYMBOL>/<SYMBOL>_YYYYMM_ticks.parquet`
- Event parquet produced by WFO prep:
- `data/analysis/tick_opportunity_mining/wfo_*/<SYMBOL>_oco_events_eval*.parquet`
- Reliability audit artifacts:
- `data/analysis/tick_opportunity_mining/data_reliability_checks.csv`
- `data/analysis/tick_opportunity_mining/data_reliability_issues.csv`
- Tick-bar + velocity builders:
- `scripts/build_global_tick_bars.py`
- `scripts/build_tick_velocity_dataset.py`

## Process
- Build fixed tick bars (`100/1000/2000`) from raw ticks.
- Build causal velocity datasets from tick bars.
- Validate required columns and parse quality.
- Validate timestamp monotonicity, duplication, and hourly/session coverage.
- Compute Stage-1 drift diagnostics (`D16-D18`) for edge-context monitoring.

## Tick Builder Contract
- Tick bars are built causally from ordered ticks using fixed tick count buckets.
- Bar schema produced by `scripts/build_global_tick_bars.py` includes:
- `timestamp`, `close_ts`, `open`, `high`, `low`, `close`, `ask`, `spread`, `tick_volume`
- path fields: `high_pos_tick`, `low_pos_tick`, `hl_first`, `hl_pos_delta_tick`, `hl_pos_frac`
- symbol aliases: `close_<SYMBOL>`, `ask_<SYMBOL>`, `spread_<SYMBOL>`
- Velocity datasets are built by `scripts/build_tick_velocity_dataset.py` from tick bars and include:
- required OCO fields: `close_ts`, `open`, `high`, `low`, `close`, `cost_est_pips`, `range_pips`, `hour_utc`, `spread_z`, `tick_rate_z`, `vel_cost_units_h1`, `hl_first`
- forward labels scaffold: `y_fwd_pips_h{h}`
- All rolling statistics are lagged by one bar (`shift(1)`) to keep features causal.

## Tick-to-Velocity Build Commands
```bash
# 1) Build fixed tick bars directly from raw ticks.
uv run python scripts/build_global_tick_bars.py \
  --tick-root /Users/danielfisher/Desktop/tick \
  --output-dir data/global_tickbars \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF \
  --base-ticks 100 \
  --aggregate-multiples 1,10,20 \
  --price-source bid \
  --timestamp-mode as_utc

# 2) Build causal velocity datasets consumed by mining/WFO.
uv run python scripts/build_tick_velocity_dataset.py \
  --tick-root /Users/danielfisher/Desktop/tick \
  --tickbar-dir data/global_tickbars \
  --out-dir data/analysis/tick_velocity \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF \
  --bar-ticks-grid 100,1000,2000 \
  --vel-horizons 1,2,5,10 \
  --target-horizons 1,2,3 \
  --vol-window 96 \
  --cost-window 288 \
  --timestamp-mode as_utc \
  --overwrite
```

## Exact Calculations
- `D16_spread_regime_shift_z`:
- `(last_month_mean(cost_est_pips) - mean(previous_months)) / std(previous_months)`
- `D17_gap_burst_ratio`:
- `mean( delta_t_seconds > 10 * median_positive_delta_t_seconds )`
- `D18_clock_jitter_cv`:
- `std(residual_ratio_clipped) / mean(residual_ratio_clipped)`
- where `residual_ratio = delta_t_seconds / median(delta_t_seconds by hour-of-week)`
- clipping is 5th-95th percentile of residual ratio
- companion metric `D18_clock_jitter_cv_raw = std(delta_t_seconds) / median_positive_delta_t_seconds`

## Causality / Leakage Controls
- Uses contemporaneous bar metadata only.
- No forward labels used in Stage 1 calculations.

## Failure Modes
- Timestamp precision collapse causes artificial zero-interval bursts.
- Duplicate timestamps reduce effective sample diversity.
- Session under-coverage creates regime bias.

## Interpretation Guide
- `D16` near 0: stable cost regime.
- `D16` large magnitude: cost regime shift requiring review.
- `D17` near 0: low gap-burst risk.
- `D18` high: unstable spacing after session baseline normalization; treat timing-sensitive execution assumptions cautiously.

## Validation Gates
Hard gates come from `DR*` checks in reliability audit.
- `DR01-DR15` are deployment-relevant quality gates.
- `D16-D18` are informational diagnostics.

## Canonical Analysis Reports
- `docs/analysis/data_reliability_report.md`

## Operator Decision Tree
- If any hard gate in this stage fails, block promotion and escalate using the operator runbook.
- If only warning/amber diagnostics trigger, continue with mitigation and add an owner/deadline in remediation artifacts.

## How To Run
- Run the `Reproduction Commands` in this stage exactly as listed.
- Confirm artifacts are refreshed and timestamps are current before interpreting outcomes.

## How To Interpret Outputs
- Read `Key Results` first for pass/fail posture and core health metrics.
- Use `Interpretation Notes` and `Action Trigger Summary` to map observed values to operational actions.

## What To Do If It Fails
- `critical/high`: halt deployment progression, remediate root cause, rerun stage and downstream dependent stages.
- `medium/low`: open tracked remediation with owner and ETA, monitor for recurrence in next cycle.

## Reproduction Commands
```bash
uv run python scripts/build_global_tick_bars.py \
  --tick-root /Users/danielfisher/Desktop/tick \
  --output-dir data/global_tickbars \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF \
  --base-ticks 100 \
  --aggregate-multiples 1,10,20 \
  --price-source bid \
  --timestamp-mode as_utc

uv run python scripts/build_tick_velocity_dataset.py \
  --tick-root /Users/danielfisher/Desktop/tick \
  --tickbar-dir data/global_tickbars \
  --out-dir data/analysis/tick_velocity \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF \
  --bar-ticks-grid 100,1000,2000 \
  --vel-horizons 1,2,5,10 \
  --target-horizons 1,2,3 \
  --vol-window 96 \
  --cost-window 288 \
  --timestamp-mode as_utc \
  --overwrite

uv run python scripts/audit_data_reliability.py \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF \
  --out-checks-csv data/analysis/tick_opportunity_mining/data_reliability_checks.csv \
  --out-issues-csv data/analysis/tick_opportunity_mining/data_reliability_issues.csv \
  --report-out docs/analysis/data_reliability_report.md
```

## Traceability
- `scripts/audit_data_reliability.py`
- `docs/analysis/data_reliability_report.md`
- `docs/strategy_bible/generated/stage_01_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_01:START -->
### Auto Snapshot - Stage 01

- generated_at: `2026-03-04 20:04:19 UTC`
- Contract check uses eval-year event tables consumed by WFO.
- Null percentages should remain near 0 for required modeling fields.
- Timezone contract rows include parse rate, monotonicity, DST and offset anomaly checks.
- Data reliability checks add schema, parse-rate, duplicate timestamp, OHLC consistency, and session coverage gates.
- Edge diagnostics D16-D18 are informational and track drift, bursty gaps, and clock jitter.

#### Key Results
| symbol   |   events_rows |   cost_est_pips_null_pct |   range_pips_null_pct |   hl_first_null_pct |   reliability_checks_total |   reliability_failed |   reliability_high_critical_failed |   d16_spread_regime_shift_z |   d17_gap_burst_ratio |   d18_clock_jitter_cv |   d18_clock_jitter_cv_raw |
|:---------|--------------:|-------------------------:|----------------------:|--------------------:|---------------------------:|---------------------:|-----------------------------------:|----------------------------:|----------------------:|----------------------:|--------------------------:|
| EURUSD   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                   -0.589219 |           0.000400833 |              0.619785 |                   8.78933 |
| GBPUSD   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                   -1.778    |           0.0002085   |              0.592694 |                   7.41284 |
| AUDUSD   |       5933630 |                        0 |                     0 |                   0 |                          0 |                    0 |                                  0 |                   -1.60736  |           8.46025e-05 |              0.616136 |                   5.00853 |
| USDJPY   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                   -1.12367  |           0.0002315   |              0.608004 |                  10.4984  |
| USDCHF   |       5979798 |                        0 |                     0 |                   0 |                          0 |                    0 |                                  0 |                   -1.3165   |           0.000130105 |              0.635497 |                   5.51376 |
| USDCAD   |       5959668 |                        0 |                     0 |                   0 |                          0 |                    0 |                                  0 |                   -1.04177  |           0.000150344 |              0.57446  |                   6.88175 |

#### Interpretation Notes
- Contract check uses eval-year event tables consumed by WFO.
- Null percentages should remain near 0 for required modeling fields.
- Timezone contract rows include parse rate, monotonicity, DST and offset anomaly checks.

#### Action Trigger Summary
| symbol   | metric_id                 | band   | severity   | action_code   | action_summary     | owner    |
|:---------|:--------------------------|:-------|:-----------|:--------------|:-------------------|:---------|
| AUDUSD   | D16_spread_regime_shift_z | green  | info       | A0_MONITOR    | within policy band | research |
| AUDUSD   | D17_gap_burst_ratio       | green  | info       | A0_MONITOR    | within policy band | data     |
| AUDUSD   | D18_clock_jitter_cv       | green  | info       | A0_MONITOR    | within policy band | data     |
| EURUSD   | D16_spread_regime_shift_z | green  | info       | A0_MONITOR    | within policy band | research |
| EURUSD   | D17_gap_burst_ratio       | green  | info       | A0_MONITOR    | within policy band | data     |
| EURUSD   | D18_clock_jitter_cv       | green  | info       | A0_MONITOR    | within policy band | data     |
| GBPUSD   | D16_spread_regime_shift_z | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | D17_gap_burst_ratio       | green  | info       | A0_MONITOR    | within policy band | data     |
| GBPUSD   | D18_clock_jitter_cv       | green  | info       | A0_MONITOR    | within policy band | data     |
| USDCAD   | D16_spread_regime_shift_z | green  | info       | A0_MONITOR    | within policy band | research |
| USDCAD   | D17_gap_burst_ratio       | green  | info       | A0_MONITOR    | within policy band | data     |
| USDCAD   | D18_clock_jitter_cv       | green  | info       | A0_MONITOR    | within policy band | data     |

#### Details
| symbol   |   events_rows |   cost_est_pips_null_pct |   range_pips_null_pct |   spread_z_null_pct |   tick_rate_z_null_pct |   vel_cost_units_h1_null_pct |   hl_first_null_pct |   d16_spread_regime_shift_z |   d17_gap_burst_ratio |   d18_clock_jitter_cv |   d18_clock_jitter_cv_raw |   reliability_checks_total |   reliability_failed |   reliability_high_critical_failed |
|:---------|--------------:|-------------------------:|----------------------:|--------------------:|-----------------------:|-----------------------------:|--------------------:|----------------------------:|----------------------:|----------------------:|--------------------------:|---------------------------:|---------------------:|-----------------------------------:|
| EURUSD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -0.589219 |           0.000400833 |              0.619785 |                   8.78933 |                         15 |                    0 |                                  0 |
| GBPUSD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.778    |           0.0002085   |              0.592694 |                   7.41284 |                         15 |                    0 |                                  0 |
| AUDUSD   |       5933630 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.60736  |           8.46025e-05 |              0.616136 |                   5.00853 |                          0 |                    0 |                                  0 |
| USDJPY   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.12367  |           0.0002315   |              0.608004 |                  10.4984  |                         15 |                    0 |                                  0 |
| USDCHF   |       5979798 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.3165   |           0.000130105 |              0.635497 |                   5.51376 |                          0 |                    0 |                                  0 |
| USDCAD   |       5959668 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.04177  |           0.000150344 |              0.57446  |                   6.88175 |                          0 |                    0 |                                  0 |

#### Plots
![stage_01_contract_health](../figures/oco_bible/stage_01_contract_health.png)
![stage_01_data_reliability](../figures/oco_bible/stage_01_data_reliability.png)

#### Data Reliability Failed Checks
_empty_
<!-- GENERATED:STAGE_01:END -->

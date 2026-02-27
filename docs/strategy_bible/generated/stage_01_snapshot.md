### Auto Snapshot - Stage 01

- generated_at: `2026-02-27 14:15:43 UTC`
- Contract check uses eval-year event tables consumed by WFO.
- Null percentages should remain near 0 for required modeling fields.
- Timezone contract rows include parse rate, monotonicity, DST and offset anomaly checks.
- Data reliability checks add schema, parse-rate, duplicate timestamp, OHLC consistency, and session coverage gates.
- Edge diagnostics D16-D18 are informational and track drift, bursty gaps, and clock jitter.

#### Key Results
| symbol   |   events_rows |   cost_est_pips_null_pct |   range_pips_null_pct |   hl_first_null_pct |   reliability_checks_total |   reliability_failed |   reliability_high_critical_failed |   d16_spread_regime_shift_z |   d17_gap_burst_ratio |   d18_clock_jitter_cv |   d18_clock_jitter_cv_raw |
|:---------|--------------:|-------------------------:|----------------------:|--------------------:|---------------------------:|---------------------:|-----------------------------------:|----------------------------:|----------------------:|----------------------:|--------------------------:|
| EURUSD   |       5536229 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                    -1.12735 |           0.000298398 |              0.63644  |                   7.90046 |
| GBPUSD   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                    -1.778   |           0.0002085   |              0.592694 |                   7.41284 |
| USDJPY   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                    -1.12367 |           0.0002315   |              0.608004 |                  10.4984  |

#### Interpretation Notes
- Contract check uses eval-year event tables consumed by WFO.
- Null percentages should remain near 0 for required modeling fields.
- Timezone contract rows include parse rate, monotonicity, DST and offset anomaly checks.

#### Action Trigger Summary
| symbol   | metric_id                 | band   | severity   | action_code   | action_summary     | owner    |
|:---------|:--------------------------|:-------|:-----------|:--------------|:-------------------|:---------|
| EURUSD   | D16_spread_regime_shift_z | green  | info       | A0_MONITOR    | within policy band | research |
| EURUSD   | D17_gap_burst_ratio       | green  | info       | A0_MONITOR    | within policy band | data     |
| EURUSD   | D18_clock_jitter_cv       | green  | info       | A0_MONITOR    | within policy band | data     |
| GBPUSD   | D16_spread_regime_shift_z | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | D17_gap_burst_ratio       | green  | info       | A0_MONITOR    | within policy band | data     |
| GBPUSD   | D18_clock_jitter_cv       | green  | info       | A0_MONITOR    | within policy band | data     |
| USDJPY   | D16_spread_regime_shift_z | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | D17_gap_burst_ratio       | green  | info       | A0_MONITOR    | within policy band | data     |
| USDJPY   | D18_clock_jitter_cv       | green  | info       | A0_MONITOR    | within policy band | data     |

#### Details
| symbol   |   events_rows |   cost_est_pips_null_pct |   range_pips_null_pct |   spread_z_null_pct |   tick_rate_z_null_pct |   vel_cost_units_h1_null_pct |   hl_first_null_pct |   d16_spread_regime_shift_z |   d17_gap_burst_ratio |   d18_clock_jitter_cv |   d18_clock_jitter_cv_raw |   reliability_checks_total |   reliability_failed |   reliability_high_critical_failed |
|:---------|--------------:|-------------------------:|----------------------:|--------------------:|-----------------------:|-----------------------------:|--------------------:|----------------------------:|----------------------:|----------------------:|--------------------------:|---------------------------:|---------------------:|-----------------------------------:|
| EURUSD   |       5536229 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                    -1.12735 |           0.000298398 |              0.63644  |                   7.90046 |                         15 |                    0 |                                  0 |
| GBPUSD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                    -1.778   |           0.0002085   |              0.592694 |                   7.41284 |                         15 |                    0 |                                  0 |
| USDJPY   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                    -1.12367 |           0.0002315   |              0.608004 |                  10.4984  |                         15 |                    0 |                                  0 |

#### Plots
![stage_01_contract_health](../../figures/oco_bible/stage_01_contract_health.png)
![stage_01_data_reliability](../../figures/oco_bible/stage_01_data_reliability.png)

#### Data Reliability Failed Checks
_empty_

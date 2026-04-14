### Auto Snapshot - Stage 01

- generated_at: `2026-04-12 17:21:09 UTC`
- Contract check uses eval-year event tables consumed by WFO.
- Null percentages should remain near 0 for required modeling fields.
- Timezone contract rows include parse rate, monotonicity, DST and offset anomaly checks.
- Data reliability checks add schema, parse-rate, duplicate timestamp, OHLC consistency, and session coverage gates.
- Edge diagnostics D16-D18 are informational and track drift, bursty gaps, and clock jitter.

#### Key Results
| symbol   |   events_rows |   cost_est_pips_null_pct |   range_pips_null_pct |   hl_first_null_pct |   reliability_checks_total |   reliability_failed |   reliability_high_critical_failed |   d16_spread_regime_shift_z |   d17_gap_burst_ratio |   d18_clock_jitter_cv |   d18_clock_jitter_cv_raw |
|:---------|--------------:|-------------------------:|----------------------:|--------------------:|---------------------------:|---------------------:|-----------------------------------:|----------------------------:|----------------------:|----------------------:|--------------------------:|
| EURUSD   |       1875665 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                  -0.237375  |           0.00263533  |              0.751579 |                  14.365   |
| GBPUSD   |       2020149 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                  -0.618732  |           0.00188452  |              0.740094 |                  13.1356  |
| AUDUSD   |        509960 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                  -0.234699  |           0.000209821 |              0.573029 |                   2.31249 |
| USDJPY   |       3400534 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                   0.0389841 |           0.000957203 |              0.707767 |                  14.128   |
| USDCHF   |        488814 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                  -0.634057  |           0.00662012  |              0.891619 |                  12.9278  |
| USDCAD   |        838415 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                  -1.24909   |           0.00333845  |              0.849638 |                  10.5752  |

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
| EURUSD   |       1875665 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                  -0.237375  |           0.00263533  |              0.751579 |                  14.365   |                         15 |                    0 |                                  0 |
| GBPUSD   |       2020149 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                  -0.618732  |           0.00188452  |              0.740094 |                  13.1356  |                         15 |                    0 |                                  0 |
| AUDUSD   |        509960 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                  -0.234699  |           0.000209821 |              0.573029 |                   2.31249 |                         15 |                    0 |                                  0 |
| USDJPY   |       3400534 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   0.0389841 |           0.000957203 |              0.707767 |                  14.128   |                         15 |                    0 |                                  0 |
| USDCHF   |        488814 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                  -0.634057  |           0.00662012  |              0.891619 |                  12.9278  |                         15 |                    0 |                                  0 |
| USDCAD   |        838415 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                  -1.24909   |           0.00333845  |              0.849638 |                  10.5752  |                         15 |                    0 |                                  0 |

#### Plots
![stage_01_contract_health](../../figures/oco_bible/stage_01_contract_health.png)
![stage_01_data_reliability](../../figures/oco_bible/stage_01_data_reliability.png)

#### Data Reliability Failed Checks
_empty_

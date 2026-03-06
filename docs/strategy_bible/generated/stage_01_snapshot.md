### Auto Snapshot - Stage 01

- generated_at: `2026-03-06 13:50:11 UTC`
- Contract check uses eval-year event tables consumed by WFO.
- Null percentages should remain near 0 for required modeling fields.
- Timezone contract rows include parse rate, monotonicity, DST and offset anomaly checks.
- Data reliability checks add schema, parse-rate, duplicate timestamp, OHLC consistency, and session coverage gates.
- Edge diagnostics D16-D18 are informational and track drift, bursty gaps, and clock jitter.

#### Key Results
| symbol   |   events_rows |   cost_est_pips_null_pct |   range_pips_null_pct |   hl_first_null_pct |   reliability_checks_total |   reliability_failed |   reliability_high_critical_failed |   d16_spread_regime_shift_z |   d17_gap_burst_ratio |   d18_clock_jitter_cv |   d18_clock_jitter_cv_raw |
|:---------|--------------:|-------------------------:|----------------------:|--------------------:|---------------------------:|---------------------:|-----------------------------------:|----------------------------:|----------------------:|----------------------:|--------------------------:|
| EURUSD   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                   -0.564371 |           0.0003995   |              0.620643 |                   8.82997 |
| GBPUSD   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                   -1.39328  |           0.000325333 |              0.593775 |                   9.01797 |
| AUDUSD   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                   -1.13896  |           0.000131    |              0.610206 |                   6.03632 |
| USDJPY   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                   -0.763532 |           0.000360833 |              0.610349 |                  13.0358  |
| USDCHF   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                   -1.20704  |           0.000224333 |              0.621472 |                   6.43203 |
| USDCAD   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |                   -1.3148   |           0.000342333 |              0.581902 |                   8.07158 |

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
| EURUSD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -0.564371 |           0.0003995   |              0.620643 |                   8.82997 |                         15 |                    0 |                                  0 |
| GBPUSD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.39328  |           0.000325333 |              0.593775 |                   9.01797 |                         15 |                    0 |                                  0 |
| AUDUSD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.13896  |           0.000131    |              0.610206 |                   6.03632 |                         15 |                    0 |                                  0 |
| USDJPY   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -0.763532 |           0.000360833 |              0.610349 |                  13.0358  |                         15 |                    0 |                                  0 |
| USDCHF   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.20704  |           0.000224333 |              0.621472 |                   6.43203 |                         15 |                    0 |                                  0 |
| USDCAD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.3148   |           0.000342333 |              0.581902 |                   8.07158 |                         15 |                    0 |                                  0 |

#### Plots
![stage_01_contract_health](../../figures/oco_bible/stage_01_contract_health.png)
![stage_01_data_reliability](../../figures/oco_bible/stage_01_data_reliability.png)

#### Data Reliability Failed Checks
_empty_

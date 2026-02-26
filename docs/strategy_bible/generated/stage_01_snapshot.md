### Auto Snapshot - Stage 01

- generated_at: `2026-02-26 22:19:06 UTC`
- Contract check uses eval-year event tables consumed by WFO.
- Null percentages should remain near 0 for required modeling fields.
- Timezone contract rows include parse rate, monotonicity, DST and offset anomaly checks.
- Data reliability checks add schema, parse-rate, duplicate timestamp, OHLC consistency, and session coverage gates.

#### Key Results
| symbol   |   events_rows |   cost_est_pips_null_pct |   range_pips_null_pct |   hl_first_null_pct |   reliability_checks_total |   reliability_failed |   reliability_high_critical_failed |
|:---------|--------------:|-------------------------:|----------------------:|--------------------:|---------------------------:|---------------------:|-----------------------------------:|
| EURUSD   |       5536229 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |
| GBPUSD   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |
| USDJPY   |       6000000 |                        0 |                     0 |                   0 |                         15 |                    0 |                                  0 |

#### Details
| symbol   |   events_rows |   cost_est_pips_null_pct |   range_pips_null_pct |   spread_z_null_pct |   tick_rate_z_null_pct |   vel_cost_units_h1_null_pct |   hl_first_null_pct |   reliability_checks_total |   reliability_failed |   reliability_high_critical_failed |
|:---------|--------------:|-------------------------:|----------------------:|--------------------:|-----------------------:|-----------------------------:|--------------------:|---------------------------:|---------------------:|-----------------------------------:|
| EURUSD   |       5536229 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                         15 |                    0 |                                  0 |
| GBPUSD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                         15 |                    0 |                                  0 |
| USDJPY   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                         15 |                    0 |                                  0 |

#### Plots
![stage_01_contract_health](../../figures/oco_bible/stage_01_contract_health.png)
![stage_01_data_reliability](../../figures/oco_bible/stage_01_data_reliability.png)

#### Data Reliability Failed Checks
_empty_

### Auto Snapshot - Stage 01

- generated_at: `2026-03-15 12:55:53 UTC`
- Contract check uses eval-year event tables consumed by WFO.
- Null percentages should remain near 0 for required modeling fields.
- Timezone contract rows include parse rate, monotonicity, DST and offset anomaly checks.
- Data reliability checks add schema, parse-rate, duplicate timestamp, OHLC consistency, and session coverage gates.
- Edge diagnostics D16-D18 are informational and track drift, bursty gaps, and clock jitter.

#### Key Results
| symbol   |   events_rows |   cost_est_pips_null_pct |   range_pips_null_pct |   hl_first_null_pct |   reliability_checks_total |   reliability_failed |   reliability_high_critical_failed |   d16_spread_regime_shift_z |   d17_gap_burst_ratio |   d18_clock_jitter_cv |   d18_clock_jitter_cv_raw |
|:---------|--------------:|-------------------------:|----------------------:|--------------------:|---------------------------:|---------------------:|-----------------------------------:|----------------------------:|----------------------:|----------------------:|--------------------------:|
| EURUSD   |       6000000 |                        0 |                     0 |                   0 |                          0 |                    0 |                                  0 |                   -0.549041 |           0.000385167 |              0.628797 |                   8.74078 |
| GBPUSD   |       6000000 |                        0 |                     0 |                   0 |                          0 |                    0 |                                  0 |                   -1.38055  |           0.000313    |              0.594427 |                   8.96348 |
| USDJPY   |       6000000 |                        0 |                     0 |                   0 |                          0 |                    0 |                                  0 |                   -0.786695 |           0.000367667 |              0.608883 |                  12.9782  |
| USDCHF   |       6000000 |                        0 |                     0 |                   0 |                          0 |                    0 |                                  0 |                   -1.17995  |           0.000231667 |              0.6276   |                   6.40526 |
| AUDUSD   |       6000000 |                        0 |                     0 |                   0 |                          0 |                    0 |                                  0 |                   -1.14727  |           0.000160333 |              0.620673 |                   6.05961 |
| USDCAD   |       6000000 |                        0 |                     0 |                   0 |                          0 |                    0 |                                  0 |                   -1.29273  |           0.000290167 |              0.588428 |                   8.01665 |

#### Interpretation Notes
- Contract check uses eval-year event tables consumed by WFO.
- Null percentages should remain near 0 for required modeling fields.
- Timezone contract rows include parse rate, monotonicity, DST and offset anomaly checks.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Details
| symbol   |   events_rows |   cost_est_pips_null_pct |   range_pips_null_pct |   spread_z_null_pct |   tick_rate_z_null_pct |   vel_cost_units_h1_null_pct |   hl_first_null_pct |   d16_spread_regime_shift_z |   d17_gap_burst_ratio |   d18_clock_jitter_cv |   d18_clock_jitter_cv_raw |   reliability_checks_total |   reliability_failed |   reliability_high_critical_failed |
|:---------|--------------:|-------------------------:|----------------------:|--------------------:|-----------------------:|-----------------------------:|--------------------:|----------------------------:|----------------------:|----------------------:|--------------------------:|---------------------------:|---------------------:|-----------------------------------:|
| EURUSD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -0.549041 |           0.000385167 |              0.628797 |                   8.74078 |                          0 |                    0 |                                  0 |
| GBPUSD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.38055  |           0.000313    |              0.594427 |                   8.96348 |                          0 |                    0 |                                  0 |
| USDJPY   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -0.786695 |           0.000367667 |              0.608883 |                  12.9782  |                          0 |                    0 |                                  0 |
| USDCHF   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.17995  |           0.000231667 |              0.6276   |                   6.40526 |                          0 |                    0 |                                  0 |
| AUDUSD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.14727  |           0.000160333 |              0.620673 |                   6.05961 |                          0 |                    0 |                                  0 |
| USDCAD   |       6000000 |                        0 |                     0 |                   0 |                      0 |                            0 |                   0 |                   -1.29273  |           0.000290167 |              0.588428 |                   8.01665 |                          0 |                    0 |                                  0 |

#### Plots
![stage_01_contract_health](../../figures/oco_bible/stage_01_contract_health.png)
![stage_01_data_reliability](../../figures/oco_bible/stage_01_data_reliability.png)

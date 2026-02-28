### Auto Snapshot - Stage 04

- generated_at: `2026-02-28 20:57:22 UTC`
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.
- E11-E13 are informational execution diagnostics: session dispersion, plateau width, and non-fill opportunity cost.
- Policy status artifact: data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv
- Session cap artifact: data/analysis/tick_opportunity_mining/stage04_cap_policy_by_session.csv

#### Key Results
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_p95_pips |   e11_session_overshoot_dispersion |   e12_cap_plateau_width_pips |   e13_nonfill_opportunity_cost_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|--------------------------:|-----------------------------------:|-----------------------------:|------------------------------------:|
| EURUSD   | 346993 |           0.999939 |               0.809054 |                   0.178786 |                       0.6 |                          0.199265  |                          1.2 |                            0.116807 |
| GBPUSD   | 346993 |           0.999939 |               0.809054 |                   0.178786 |                       0.6 |                          0.148447  |                          1.2 |                            0.116433 |
| AUDUSD   | 398006 |           0        |               0.645227 |                 nan        |                     nan   |                        nan         |                        nan   |                          nan        |
| USDJPY   | 346993 |           0.999939 |               0.809054 |                   0.178786 |                       0.6 |                          0.0882319 |                          1.2 |                            0.182388 |
| USDCHF   | 346993 |           0.999939 |               0.809054 |                   0.178786 |                       0.6 |                          1.0242    |                          1.2 |                            0.109211 |
| USDCAD   | 346993 |           0.999939 |               0.809054 |                   0.178786 |                       0.6 |                          0.363498  |                          1   |                            0.137788 |

#### Interpretation Notes
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.

#### Action Trigger Summary
| symbol   | metric_id                         | band   | severity   | action_code   | action_summary     | owner     |
|:---------|:----------------------------------|:-------|:-----------|:--------------|:-------------------|:----------|
| EURUSD   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR    | within policy band | execution |
| EURUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR    | within policy band | execution |
| EURUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR    | within policy band | execution |
| GBPUSD   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR    | within policy band | execution |
| GBPUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR    | within policy band | execution |
| GBPUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR    | within policy band | execution |
| USDJPY   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR    | within policy band | execution |
| USDJPY   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR    | within policy band | execution |
| USDJPY   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR    | within policy band | execution |

#### Details
| symbol   |   cap_pips |   fill_rate |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|---------------------------------:|
| AUDUSD   |        0.5 |    0        |                       nan        |
| AUDUSD   |        0.8 |    0        |                       nan        |
| AUDUSD   |        1   |    0        |                       nan        |
| AUDUSD   |        1.2 |    0        |                       nan        |
| AUDUSD   |        1.5 |    0        |                       nan        |
| AUDUSD   |        2   |    0        |                       nan        |
| EURUSD   |        0.5 |    0.942824 |                         0.798632 |
| EURUSD   |        0.8 |    0.975843 |                         0.849812 |
| EURUSD   |        1   |    0.986275 |                         0.865469 |
| EURUSD   |        1.2 |    0.990054 |                         0.877019 |
| EURUSD   |        1.5 |    0.993919 |                         0.889102 |
| EURUSD   |        2   |    0.997058 |                         0.888653 |
| GBPUSD   |        0.5 |    0.951886 |                         0.623176 |
| GBPUSD   |        0.8 |    0.981929 |                         0.663135 |
| GBPUSD   |        1   |    0.990513 |                         0.666388 |
| GBPUSD   |        1.2 |    0.992546 |                         0.666637 |
| GBPUSD   |        1.5 |    0.994805 |                         0.671516 |
| GBPUSD   |        2   |    0.996612 |                         0.677863 |
| USDCAD   |        0.5 |    0.921385 |                         0.556883 |
| USDCAD   |        0.8 |    0.96325  |                         0.591826 |
| USDCAD   |        1   |    0.975668 |                         0.603404 |
| USDCAD   |        1.2 |    0.979827 |                         0.611363 |
| USDCAD   |        1.5 |    0.985285 |                         0.626289 |
| USDCAD   |        2   |    0.991328 |                         0.632537 |
| USDCHF   |        0.5 |    0.946351 |                         0.678917 |
| USDCHF   |        0.8 |    0.96817  |                         0.706963 |
| USDCHF   |        1   |    0.974277 |                         0.707902 |
| USDCHF   |        1.2 |    0.977236 |                         0.71137  |
| USDCHF   |        1.5 |    0.982412 |                         0.725124 |
| USDCHF   |        2   |    0.986462 |                         0.728158 |
| USDJPY   |        0.5 |    0.924884 |                         1.12179  |
| USDJPY   |        0.8 |    0.966592 |                         1.16615  |
| USDJPY   |        1   |    0.977121 |                         1.17311  |
| USDJPY   |        1.2 |    0.98198  |                         1.17589  |
| USDJPY   |        1.5 |    0.988662 |                         1.18882  |
| USDJPY   |        2   |    0.992306 |                         1.19557  |

#### Plots
![stage_04_stop_limit_caps](../../figures/oco_bible/stage_04_stop_limit_caps.png)
![stage_04_execution_policy_bands](../../figures/oco_bible/stage_04_execution_policy_bands.png)

#### Execution Risk Pre-Live
| symbol   |   checks_total |   checks_failed |   high_critical_failed |   e02_min_month_fill_rate |   e03_tail_above_cap |   e10_lb95_month_signal_net |
|:---------|---------------:|----------------:|-----------------------:|--------------------------:|---------------------:|----------------------------:|
| EURUSD   |             10 |               0 |                      0 |                  0.983069 |           0.0121925  |                    0.559403 |
| GBPUSD   |             10 |               0 |                      0 |                  0.984447 |           0.00801961 |                    0.781192 |
| USDJPY   |             10 |               0 |                      0 |                  0.969299 |           0.0191173  |                    1.00093  |

#### Policy Status
| symbol   |   metrics_total |   green_metric_count |   amber_metric_count |   red_metric_count | worst_band   | recommended_action_code   | recommended_action_summary                                            | red_metrics   | amber_metrics                    |
|:---------|----------------:|---------------------:|---------------------:|-------------------:|:-------------|:--------------------------|:----------------------------------------------------------------------|:--------------|:---------------------------------|
| AUDUSD   |               5 |                    0 |                    0 |                  0 | unknown      | A9_DATA_GAP               | missing metric value; regenerate Stage 04 artifacts before deployment |               |                                  |
| EURUSD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only                          |               |                                  |
| GBPUSD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only                          |               |                                  |
| USDCAD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only                          |               |                                  |
| USDCHF   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | session overshoot uneven; add session guard and re-check E11          |               | E11_session_overshoot_dispersion |
| USDJPY   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only                          |               |                                  |

- policy_csv: `data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv`

#### Policy Metric Mapping (Detail)
| symbol   | metric_id                         |   metric_value | band    | action_code      | green_threshold   | amber_threshold   |
|:---------|:----------------------------------|---------------:|:--------|:-----------------|:------------------|:------------------|
| EURUSD   | E11_session_overshoot_dispersion  |      0.199265  | green   | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| EURUSD   | E12_cap_plateau_width_pips        |      1.2       | green   | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| EURUSD   | E13_nonfill_opportunity_cost_pips |      0.116807  | green   | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| EURUSD   | erosion_spread_fee_plus_slip      |     -0.0800481 | green   | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| EURUSD   | tick_overshoot_p95_pips           |      0.6       | green   | A0_MONITOR       | <= 0.7000         | <= 1.0000         |
| GBPUSD   | E11_session_overshoot_dispersion  |      0.148447  | green   | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| GBPUSD   | E12_cap_plateau_width_pips        |      1.2       | green   | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| GBPUSD   | E13_nonfill_opportunity_cost_pips |      0.116433  | green   | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| GBPUSD   | erosion_spread_fee_plus_slip      |      0.131191  | green   | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| GBPUSD   | tick_overshoot_p95_pips           |      0.6       | green   | A0_MONITOR       | <= 0.7000         | <= 1.0000         |
| AUDUSD   | E11_session_overshoot_dispersion  |    nan         | unknown | A9_DATA_GAP      |                   |                   |
| AUDUSD   | E12_cap_plateau_width_pips        |    nan         | unknown | A9_DATA_GAP      |                   |                   |
| AUDUSD   | E13_nonfill_opportunity_cost_pips |    nan         | unknown | A9_DATA_GAP      |                   |                   |
| AUDUSD   | erosion_spread_fee_plus_slip      |    nan         | unknown | A9_DATA_GAP      |                   |                   |
| AUDUSD   | tick_overshoot_p95_pips           |    nan         | unknown | A9_DATA_GAP      |                   |                   |
| USDJPY   | E11_session_overshoot_dispersion  |      0.0882319 | green   | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| USDJPY   | E12_cap_plateau_width_pips        |      1.2       | green   | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| USDJPY   | E13_nonfill_opportunity_cost_pips |      0.182388  | green   | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| USDJPY   | erosion_spread_fee_plus_slip      |     -0.386512  | green   | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| USDJPY   | tick_overshoot_p95_pips           |      0.6       | green   | A0_MONITOR       | <= 0.7000         | <= 1.0000         |
| USDCHF   | E11_session_overshoot_dispersion  |      1.0242    | amber   | A2_SESSION_GUARD | <= 1.0000         | <= 1.3000         |
| USDCHF   | E12_cap_plateau_width_pips        |      1.2       | green   | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| USDCHF   | E13_nonfill_opportunity_cost_pips |      0.109211  | green   | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| USDCHF   | erosion_spread_fee_plus_slip      |      0.0808968 | green   | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| USDCHF   | tick_overshoot_p95_pips           |      0.6       | green   | A0_MONITOR       | <= 0.7000         | <= 1.0000         |
| USDCAD   | E11_session_overshoot_dispersion  |      0.363498  | green   | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| USDCAD   | E12_cap_plateau_width_pips        |      1         | green   | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| USDCAD   | E13_nonfill_opportunity_cost_pips |      0.137788  | green   | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| USDCAD   | erosion_spread_fee_plus_slip      |      0.176517  | green   | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| USDCAD   | tick_overshoot_p95_pips           |      0.6       | green   | A0_MONITOR       | <= 0.7000         | <= 1.0000         |

#### Session Rolling Cap Policy
| symbol   | session_bucket   |   lookback_days |   cap_quantile |   cap_pips |   rows_used |   session_cap_rows |   global_cap_rows |   fallback_rows |
|:---------|:-----------------|----------------:|---------------:|-----------:|------------:|-------------------:|------------------:|----------------:|
| EURUSD   | ASIA             |              20 |            0.9 |        0.2 |      114171 |             113971 |                 2 |             198 |
| EURUSD   | LATE             |              20 |            0.9 |        0.1 |       11207 |              10377 |               830 |               0 |
| EURUSD   | LONDON           |              20 |            0.9 |        0.2 |      108028 |             107828 |               200 |               0 |
| EURUSD   | NY               |              20 |            0.9 |        0.2 |       91288 |              91088 |               200 |               0 |
| GBPUSD   | ASIA             |              20 |            0.9 |        0.3 |        1566 |                131 |              1349 |              86 |
| GBPUSD   | LATE             |              20 |            0.9 |        0.3 |         164 |                  0 |               162 |               2 |
| GBPUSD   | LONDON           |              20 |            0.9 |        0.3 |        1883 |                 39 |              1782 |              62 |
| GBPUSD   | NY               |              20 |            0.9 |        0.3 |         808 |                  0 |               746 |              62 |
| USDJPY   | ASIA             |              20 |            0.9 |        0.5 |        1712 |                  4 |              1646 |              62 |
| USDJPY   | LATE             |              20 |            0.9 |        0.5 |         239 |                  0 |               230 |               9 |
| USDJPY   | LONDON           |              20 |            0.9 |        0.5 |        1591 |                248 |              1276 |              67 |
| USDJPY   | NY               |              20 |            0.9 |        0.5 |        1395 |                119 |              1205 |              71 |
| USDCHF   | ASIA             |              20 |            0.9 |        0.2 |      165298 |             165098 |                 1 |             199 |
| USDCHF   | LATE             |              20 |            0.9 |        0.3 |        4630 |               3906 |               724 |               0 |
| USDCHF   | LONDON           |              20 |            0.9 |        0.2 |      152685 |             152485 |               200 |               0 |
| USDCHF   | NY               |              20 |            0.9 |        2.6 |       42069 |              41869 |               200 |               0 |
| USDCAD   | ASIA             |              20 |            0.9 |        0.2 |       48295 |              48095 |                62 |             138 |
| USDCAD   | LATE             |              20 |            0.9 |        0.3 |        4794 |               4005 |               789 |               0 |
| USDCAD   | LONDON           |              20 |            0.9 |        0.2 |      174580 |             174380 |               138 |              62 |
| USDCAD   | NY               |              20 |            0.9 |        0.3 |      119175 |             118975 |               200 |               0 |

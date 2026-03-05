### Auto Snapshot - Stage 04

- generated_at: `2026-03-05 14:41:51 UTC`
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.
- E11-E13 are informational execution diagnostics: session dispersion, plateau width, and non-fill opportunity cost.
- Policy status artifact: data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv
- Session cap artifact: data/analysis/tick_opportunity_mining/stage04_cap_policy_by_session.csv

#### Key Results
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_p95_pips |   e11_session_overshoot_dispersion |   e12_cap_plateau_width_pips |   e13_nonfill_opportunity_cost_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|--------------------------:|-----------------------------------:|-----------------------------:|------------------------------------:|
| EURUSD   | 379629 |           0.996657 |               0.824065 |                   0.188771 |                       0.7 |                           0.202143 |                          1.2 |                           0.121883  |
| GBPUSD   | 379629 |           0.996657 |               0.824065 |                   0.188771 |                       0.7 |                           0.278869 |                          1.2 |                           0.119252  |
| AUDUSD   | 379629 |           0.996657 |               0.824065 |                   0.188771 |                       0.7 |                           0.288899 |                          1.2 |                           0.0933759 |
| USDJPY   | 379629 |           0.996657 |               0.824065 |                   0.188771 |                       0.7 |                           0.136441 |                          1.2 |                           0.190838  |
| USDCHF   | 379629 |           0.996657 |               0.824065 |                   0.188771 |                       0.7 |                           0.976806 |                          1.2 |                           0.110524  |
| USDCAD   | 379629 |           0.996657 |               0.824065 |                   0.188771 |                       0.7 |                           0.356605 |                          1   |                           0.145914  |

#### Interpretation Notes
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.

#### Action Trigger Summary
| symbol   | metric_id                         | band   | severity   | action_code    | action_summary     | owner     |
|:---------|:----------------------------------|:-------|:-----------|:---------------|:-------------------|:----------|
| AUDUSD   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR     | within policy band | execution |
| AUDUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR     | within policy band | execution |
| AUDUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR     | within policy band | execution |
| EURUSD   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR     | within policy band | execution |
| EURUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR     | within policy band | execution |
| EURUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR     | within policy band | execution |
| GBPUSD   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR     | within policy band | execution |
| GBPUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR     | within policy band | execution |
| GBPUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR     | within policy band | execution |
| USDCAD   | E11_session_overshoot_dispersion  | amber  | medium     | A2_RECALIBRATE | review and monitor | execution |
| USDCAD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR     | within policy band | execution |
| USDCAD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR     | within policy band | execution |

#### Details
| symbol   |   cap_pips |   fill_rate |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|---------------------------------:|
| AUDUSD   |        0.5 |    0.95624  |                         0.518406 |
| AUDUSD   |        0.8 |    0.97411  |                         0.531925 |
| AUDUSD   |        1   |    0.979224 |                         0.540876 |
| AUDUSD   |        1.2 |    0.981119 |                         0.546253 |
| AUDUSD   |        1.5 |    0.984147 |                         0.547482 |
| AUDUSD   |        2   |    0.986348 |                         0.549962 |
| EURUSD   |        0.5 |    0.939663 |                         1.15874  |
| EURUSD   |        0.8 |    0.972793 |                         1.21456  |
| EURUSD   |        1   |    0.983799 |                         1.22979  |
| EURUSD   |        1.2 |    0.987792 |                         1.24333  |
| EURUSD   |        1.5 |    0.992115 |                         1.26369  |
| EURUSD   |        2   |    0.995712 |                         1.26526  |
| GBPUSD   |        0.5 |    0.947971 |                         0.836742 |
| GBPUSD   |        0.8 |    0.980369 |                         0.863707 |
| GBPUSD   |        1   |    0.988455 |                         0.879063 |
| GBPUSD   |        1.2 |    0.990569 |                         0.880922 |
| GBPUSD   |        1.5 |    0.993143 |                         0.884192 |
| GBPUSD   |        2   |    0.995389 |                         0.882237 |
| USDCAD   |        0.5 |    0.911392 |                         0.562624 |
| USDCAD   |        0.8 |    0.957993 |                         0.600578 |
| USDCAD   |        1   |    0.971833 |                         0.609734 |
| USDCAD   |        1.2 |    0.976485 |                         0.618088 |
| USDCAD   |        1.5 |    0.982083 |                         0.632659 |
| USDCAD   |        2   |    0.988128 |                         0.638021 |
| USDCHF   |        0.5 |    0.941524 |                         0.713679 |
| USDCHF   |        0.8 |    0.964412 |                         0.745307 |
| USDCHF   |        1   |    0.97072  |                         0.747465 |
| USDCHF   |        1.2 |    0.97366  |                         0.751208 |
| USDCHF   |        1.5 |    0.978847 |                         0.76447  |
| USDCHF   |        2   |    0.982725 |                         0.767479 |
| USDJPY   |        0.5 |    0.920052 |                         1.04681  |
| USDJPY   |        0.8 |    0.964269 |                         1.09684  |
| USDJPY   |        1   |    0.979043 |                         1.11966  |
| USDJPY   |        1.2 |    0.983558 |                         1.12492  |
| USDJPY   |        1.5 |    0.990274 |                         1.14272  |
| USDJPY   |        2   |    0.993999 |                         1.15058  |

#### Plots
![stage_04_stop_limit_caps](../../figures/oco_bible/stage_04_stop_limit_caps.png)
![stage_04_execution_policy_bands](../../figures/oco_bible/stage_04_execution_policy_bands.png)

#### Execution Risk Pre-Live
| symbol   |   checks_total |   checks_failed |   high_critical_failed |   e02_min_month_fill_rate |   e03_tail_above_cap |   e10_lb95_month_signal_net |
|:---------|---------------:|----------------:|-----------------------:|--------------------------:|---------------------:|----------------------------:|
| EURUSD   |             10 |               0 |                      0 |                  0.981402 |           0.0120315  |                    0.984822 |
| GBPUSD   |             10 |               0 |                      0 |                  0.984229 |           0.00942047 |                    0.787091 |
| AUDUSD   |             10 |               0 |                      0 |                  0.971047 |           0.0085751  |                    0.204919 |
| USDJPY   |             10 |               0 |                      0 |                  0.972786 |           0.016399   |                    0.952701 |
| USDCHF   |             10 |               0 |                      0 |                  0.940946 |           0.0221941  |                    0.304502 |
| USDCAD   |             10 |               0 |                      0 |                  0.970947 |           0.02024    |                    0.39901  |

#### Policy Status
| symbol   |   metrics_total |   green_metric_count |   amber_metric_count |   red_metric_count | worst_band   | recommended_action_code   | recommended_action_summary                               | red_metrics   | amber_metrics           |
|:---------|----------------:|---------------------:|---------------------:|-------------------:|:-------------|:--------------------------|:---------------------------------------------------------|:--------------|:------------------------|
| AUDUSD   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor |               | tick_overshoot_p95_pips |
| EURUSD   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor |               | tick_overshoot_p95_pips |
| GBPUSD   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor |               | tick_overshoot_p95_pips |
| USDCAD   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor |               | tick_overshoot_p95_pips |
| USDCHF   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor |               | tick_overshoot_p95_pips |
| USDJPY   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor |               | tick_overshoot_p95_pips |

- policy_csv: `data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv`

#### Policy Metric Mapping (Detail)
| symbol   | metric_id                         |   metric_value | band   | action_code      | green_threshold   | amber_threshold   |
|:---------|:----------------------------------|---------------:|:-------|:-----------------|:------------------|:------------------|
| EURUSD   | E11_session_overshoot_dispersion  |      0.202143  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| EURUSD   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| EURUSD   | E13_nonfill_opportunity_cost_pips |      0.121883  | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| EURUSD   | erosion_spread_fee_plus_slip      |     -0.441191  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| EURUSD   | tick_overshoot_p95_pips           |      0.7       | amber  | A2_SESSION_GUARD | <= 0.7000         | <= 1.0000         |
| GBPUSD   | E11_session_overshoot_dispersion  |      0.278869  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| GBPUSD   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| GBPUSD   | E13_nonfill_opportunity_cost_pips |      0.119252  | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| GBPUSD   | erosion_spread_fee_plus_slip      |     -0.0601276 | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| GBPUSD   | tick_overshoot_p95_pips           |      0.7       | amber  | A2_SESSION_GUARD | <= 0.7000         | <= 1.0000         |
| AUDUSD   | E11_session_overshoot_dispersion  |      0.288899  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| AUDUSD   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| AUDUSD   | E13_nonfill_opportunity_cost_pips |      0.0933759 | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| AUDUSD   | erosion_spread_fee_plus_slip      |      0.274103  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| AUDUSD   | tick_overshoot_p95_pips           |      0.7       | amber  | A2_SESSION_GUARD | <= 0.7000         | <= 1.0000         |
| USDJPY   | E11_session_overshoot_dispersion  |      0.136441  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| USDJPY   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| USDJPY   | E13_nonfill_opportunity_cost_pips |      0.190838  | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| USDJPY   | erosion_spread_fee_plus_slip      |     -0.326515  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| USDJPY   | tick_overshoot_p95_pips           |      0.7       | amber  | A2_SESSION_GUARD | <= 0.7000         | <= 1.0000         |
| USDCHF   | E11_session_overshoot_dispersion  |      0.976806  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| USDCHF   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| USDCHF   | E13_nonfill_opportunity_cost_pips |      0.110524  | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| USDCHF   | erosion_spread_fee_plus_slip      |      0.0565859 | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| USDCHF   | tick_overshoot_p95_pips           |      0.7       | amber  | A2_SESSION_GUARD | <= 0.7000         | <= 1.0000         |
| USDCAD   | E11_session_overshoot_dispersion  |      0.356605  | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| USDCAD   | E12_cap_plateau_width_pips        |      1         | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| USDCAD   | E13_nonfill_opportunity_cost_pips |      0.145914  | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| USDCAD   | erosion_spread_fee_plus_slip      |      0.186044  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| USDCAD   | tick_overshoot_p95_pips           |      0.7       | amber  | A2_SESSION_GUARD | <= 0.7000         | <= 1.0000         |

#### Session Rolling Cap Policy
| symbol   | session_bucket   |   lookback_days |   cap_quantile |   cap_pips |   rows_used |   session_cap_rows |   global_cap_rows |   fallback_rows |
|:---------|:-----------------|----------------:|---------------:|-----------:|------------:|-------------------:|------------------:|----------------:|
| EURUSD   | ASIA             |              20 |            0.9 |       0.2  |      128713 |             128513 |                72 |             128 |
| EURUSD   | LATE             |              20 |            0.9 |       0.2  |       15033 |              14133 |               900 |               0 |
| EURUSD   | LONDON           |              20 |            0.9 |       0.3  |      165311 |             165111 |               200 |               0 |
| EURUSD   | NY               |              20 |            0.9 |       0.7  |      120485 |             120285 |               128 |              72 |
| GBPUSD   | ASIA             |              20 |            0.9 |       0.3  |      161014 |             160814 |                 6 |             194 |
| GBPUSD   | LATE             |              20 |            0.9 |       0.4  |        5804 |               4883 |               921 |               0 |
| GBPUSD   | LONDON           |              20 |            0.9 |       0.3  |      164544 |             164344 |               200 |               0 |
| GBPUSD   | NY               |              20 |            0.9 |       0.4  |       60439 |              60239 |               200 |               0 |
| AUDUSD   | ASIA             |              20 |            0.9 |       0.2  |      125519 |             125319 |                 8 |             192 |
| AUDUSD   | LATE             |              20 |            0.9 |       0.1  |       29760 |              29560 |               200 |               0 |
| AUDUSD   | LONDON           |              20 |            0.9 |       0.2  |      153982 |             153782 |               200 |               0 |
| AUDUSD   | NY               |              20 |            0.9 |       0.4  |      130074 |             129874 |               200 |               0 |
| USDJPY   | ASIA             |              20 |            0.9 |       0.4  |      194490 |             194290 |                 0 |             200 |
| USDJPY   | LATE             |              20 |            0.9 |       0.5  |       23571 |              23371 |               200 |               0 |
| USDJPY   | LONDON           |              20 |            0.9 |       0.4  |      120207 |             120007 |               200 |               0 |
| USDJPY   | NY               |              20 |            0.9 |       0.6  |      120421 |             120221 |               200 |               0 |
| USDCHF   | ASIA             |              20 |            0.9 |       0.2  |      170015 |             169815 |                 1 |             199 |
| USDCHF   | LATE             |              20 |            0.9 |       0.2  |        4857 |               4055 |               802 |               0 |
| USDCHF   | LONDON           |              20 |            0.9 |       0.2  |      150730 |             150530 |               200 |               0 |
| USDCHF   | NY               |              20 |            0.9 |       2.33 |       43283 |              43083 |               200 |               0 |
| USDCAD   | ASIA             |              20 |            0.9 |       0.2  |       63540 |              63340 |                62 |             138 |
| USDCAD   | LATE             |              20 |            0.9 |       0.3  |        5710 |               4982 |               728 |               0 |
| USDCAD   | LONDON           |              20 |            0.9 |       0.2  |      179333 |             179133 |               138 |              62 |
| USDCAD   | NY               |              20 |            0.9 |       0.5  |      129597 |             129397 |               200 |               0 |

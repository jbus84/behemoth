### Auto Snapshot - Stage 04

- generated_at: `2026-02-27 11:41:32 UTC`
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.
- E11-E13 are informational execution diagnostics: session dispersion, plateau width, and non-fill opportunity cost.
- Policy status artifact: /Users/danielfisher/repositories/behemoth/data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv
- Session cap artifact: /Users/danielfisher/repositories/behemoth/data/analysis/tick_opportunity_mining/stage04_cap_policy_by_session.csv

#### Key Results
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_p95_pips |   e11_session_overshoot_dispersion |   e12_cap_plateau_width_pips |   e13_nonfill_opportunity_cost_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|--------------------------:|-----------------------------------:|-----------------------------:|------------------------------------:|
| EURUSD   | 324963 |           0.999985 |                1.04109 |                   0.136206 |                       0.5 |                           0.199265 |                          0.7 |                            0.116807 |
| GBPUSD   | 414128 |           0.999978 |                1.01745 |                   0.141476 |                       0.5 |                           0.26181  |                          0.7 |                            0.11825  |
| USDJPY   | 459585 |           0.999954 |                1.37853 |                   0.221513 |                       0.7 |                           0.133612 |                          0.7 |                            0.185352 |

#### Details
| symbol   |   cap_pips |   fill_rate |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|---------------------------------:|
| EURUSD   |        0.8 |    0.975843 |                         0.849812 |
| EURUSD   |        1   |    0.986275 |                         0.865469 |
| EURUSD   |        1.2 |    0.990054 |                         0.877019 |
| EURUSD   |        1.5 |    0.993919 |                         0.889102 |
| GBPUSD   |        0.8 |    0.980955 |                         0.858803 |
| GBPUSD   |        1   |    0.988796 |                         0.87368  |
| GBPUSD   |        1.2 |    0.990858 |                         0.875675 |
| GBPUSD   |        1.5 |    0.993398 |                         0.878747 |
| USDJPY   |        0.8 |    0.963719 |                         1.11047  |
| USDJPY   |        1   |    0.978787 |                         1.13374  |
| USDJPY   |        1.2 |    0.983461 |                         1.13861  |
| USDJPY   |        1.5 |    0.990209 |                         1.1564   |

#### Plots
![stage_04_stop_limit_caps](../../figures/oco_bible/stage_04_stop_limit_caps.png)
![stage_04_execution_policy_bands](../../figures/oco_bible/stage_04_execution_policy_bands.png)

#### Execution Risk Pre-Live
| symbol   |   checks_total |   checks_failed |   high_critical_failed |   e02_min_month_fill_rate |   e03_tail_above_cap |   e10_lb95_month_signal_net |
|:---------|---------------:|----------------:|-----------------------:|--------------------------:|---------------------:|----------------------------:|
| EURUSD   |             10 |               0 |                      0 |                  0.985912 |           0.00993051 |                    0.541982 |
| GBPUSD   |             10 |               0 |                      0 |                  0.985112 |           0.00912057 |                    0.787315 |
| USDJPY   |             10 |               0 |                      0 |                  0.974161 |           0.0164939  |                    0.958587 |

#### Policy Status
| symbol   |   metrics_total |   green_metric_count |   amber_metric_count |   red_metric_count | worst_band   | recommended_action_code   | recommended_action_summary                   | red_metrics   | amber_metrics   |
|:---------|----------------:|---------------------:|---------------------:|-------------------:|:-------------|:--------------------------|:---------------------------------------------|:--------------|:----------------|
| EURUSD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only |               |                 |
| GBPUSD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only |               |                 |
| USDJPY   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only |               |                 |

- policy_csv: `/Users/danielfisher/repositories/behemoth/data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv`

#### Policy Metric Mapping (Detail)
| symbol   | metric_id                         |   metric_value | band   | action_code   | green_threshold   | amber_threshold   |
|:---------|:----------------------------------|---------------:|:-------|:--------------|:------------------|:------------------|
| EURUSD   | E11_session_overshoot_dispersion  |       0.199265 | green  | A0_MONITOR    | <= 1.0000         | <= 1.3000         |
| EURUSD   | E12_cap_plateau_width_pips        |       0.7      | green  | A0_MONITOR    | >= 0.5000         | >= 0.3000         |
| EURUSD   | E13_nonfill_opportunity_cost_pips |       0.116807 | green  | A0_MONITOR    | <= 0.2000         | <= 0.3500         |
| EURUSD   | erosion_spread_fee_plus_slip      |       0.151985 | green  | A0_MONITOR    | <= 0.3000         | <= 0.5000         |
| EURUSD   | tick_overshoot_p95_pips           |       0.5      | green  | A0_MONITOR    | <= 0.7000         | <= 1.0000         |
| GBPUSD   | E11_session_overshoot_dispersion  |       0.26181  | green  | A0_MONITOR    | <= 1.0000         | <= 1.3000         |
| GBPUSD   | E12_cap_plateau_width_pips        |       0.7      | green  | A0_MONITOR    | >= 0.5000         | >= 0.3000         |
| GBPUSD   | E13_nonfill_opportunity_cost_pips |       0.11825  | green  | A0_MONITOR    | <= 0.2000         | <= 0.3500         |
| GBPUSD   | erosion_spread_fee_plus_slip      |       0.138699 | green  | A0_MONITOR    | <= 0.3000         | <= 0.5000         |
| GBPUSD   | tick_overshoot_p95_pips           |       0.5      | green  | A0_MONITOR    | <= 0.7000         | <= 1.0000         |
| USDJPY   | E11_session_overshoot_dispersion  |       0.133612 | green  | A0_MONITOR    | <= 1.0000         | <= 1.3000         |
| USDJPY   | E12_cap_plateau_width_pips        |       0.7      | green  | A0_MONITOR    | >= 0.5000         | >= 0.3000         |
| USDJPY   | E13_nonfill_opportunity_cost_pips |       0.185352 | green  | A0_MONITOR    | <= 0.2000         | <= 0.3500         |
| USDJPY   | erosion_spread_fee_plus_slip      |       0.222132 | green  | A0_MONITOR    | <= 0.3000         | <= 0.5000         |
| USDJPY   | tick_overshoot_p95_pips           |       0.7      | green  | A0_MONITOR    | <= 0.7000         | <= 1.0000         |

#### Session Rolling Cap Policy
| symbol   | session_bucket   |   lookback_days |   cap_quantile |   cap_pips |   rows_used |   session_cap_rows |   global_cap_rows |   fallback_rows |
|:---------|:-----------------|----------------:|---------------:|-----------:|------------:|-------------------:|------------------:|----------------:|
| EURUSD   | ASIA             |              20 |            0.9 |        0.2 |      114171 |             113971 |                 2 |             198 |
| EURUSD   | LATE             |              20 |            0.9 |        0.1 |       11207 |              10377 |               830 |               0 |
| EURUSD   | LONDON           |              20 |            0.9 |        0.2 |      108028 |             107828 |               200 |               0 |
| EURUSD   | NY               |              20 |            0.9 |        0.2 |       91288 |              91088 |               200 |               0 |
| GBPUSD   | ASIA             |              20 |            0.9 |        0.3 |      170822 |             170622 |                 6 |             194 |
| GBPUSD   | LATE             |              20 |            0.9 |        0.3 |        5891 |               4867 |              1024 |               0 |
| GBPUSD   | LONDON           |              20 |            0.9 |        0.3 |      173809 |             173609 |               200 |               0 |
| GBPUSD   | NY               |              20 |            0.9 |        0.6 |       63280 |              63080 |               200 |               0 |
| USDJPY   | ASIA             |              20 |            0.9 |        0.4 |      194384 |             194184 |                 0 |             200 |
| USDJPY   | LATE             |              20 |            0.9 |        0.4 |       23720 |              23520 |               200 |               0 |
| USDJPY   | LONDON           |              20 |            0.9 |        0.4 |      119880 |             119680 |               200 |               0 |
| USDJPY   | NY               |              20 |            0.9 |        0.6 |      121207 |             121007 |               200 |               0 |

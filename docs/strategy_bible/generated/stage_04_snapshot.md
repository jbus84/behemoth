### Auto Snapshot - Stage 04

- generated_at: `2026-04-12 17:21:09 UTC`
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.
- E11-E13 are informational execution diagnostics: session dispersion, plateau width, and non-fill opportunity cost.
- Policy status artifact: data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv
- Session cap artifact: data/analysis/tick_opportunity_mining/stage04_cap_policy_by_session.csv

#### Key Results
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_p95_pips |   e11_session_overshoot_dispersion |   e12_cap_plateau_width_pips |   e13_nonfill_opportunity_cost_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|--------------------------:|-----------------------------------:|-----------------------------:|------------------------------------:|
| EURUSD   |  47190 |           0.992414 |                4.03178 |                   0.116783 |                       0.4 |                          0.377896  |                          1.5 |                           0.101956  |
| GBPUSD   |  47190 |           0.992414 |                4.03178 |                   0.116783 |                       0.4 |                          0.0973022 |                          1.5 |                           0.105239  |
| AUDUSD   |  47190 |           0.992414 |                4.03178 |                   0.116783 |                       0.4 |                          0.17529   |                          1.5 |                           0.062335  |
| USDJPY   |  47190 |           0.992414 |                4.03178 |                   0.116783 |                       0.4 |                          0.253072  |                          1.2 |                           0.182184  |
| USDCHF   |  47190 |           0.992414 |                4.03178 |                   0.116783 |                       0.4 |                          0.196247  |                          1.5 |                           0.0872835 |
| USDCAD   |  47190 |           0.992414 |                4.03178 |                   0.116783 |                       0.4 |                          0.305139  |                          1.5 |                           0.100596  |

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
| EURUSD   | E11_session_overshoot_dispersion  | amber  | medium     | A2_RECALIBRATE | review and monitor | execution |
| EURUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR     | within policy band | execution |
| EURUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR     | within policy band | execution |
| GBPUSD   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR     | within policy band | execution |
| GBPUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR     | within policy band | execution |
| GBPUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR     | within policy band | execution |
| USDCAD   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR     | within policy band | execution |
| USDCAD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR     | within policy band | execution |
| USDCAD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR     | within policy band | execution |

#### Details
| symbol   |   cap_pips |   fill_rate |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|---------------------------------:|
| AUDUSD   |        0.5 |    0.952527 |                          3.52679 |
| AUDUSD   |        0.8 |    0.962625 |                          3.56055 |
| AUDUSD   |        1   |    0.9649   |                          3.57062 |
| AUDUSD   |        1.2 |    0.965766 |                          3.5713  |
| AUDUSD   |        1.5 |    0.966856 |                          3.56876 |
| AUDUSD   |        2   |    0.968362 |                          3.57071 |
| EURUSD   |        0.5 |    0.949047 |                          4.74426 |
| EURUSD   |        0.8 |    0.974144 |                          4.88585 |
| EURUSD   |        1   |    0.982937 |                          4.92456 |
| EURUSD   |        1.2 |    0.985906 |                          4.93974 |
| EURUSD   |        1.5 |    0.988884 |                          4.94022 |
| EURUSD   |        2   |    0.991311 |                          4.9654  |
| GBPUSD   |        0.5 |    0.948878 |                          5.22649 |
| GBPUSD   |        0.8 |    0.975125 |                          5.34036 |
| GBPUSD   |        1   |    0.980374 |                          5.36332 |
| GBPUSD   |        1.2 |    0.98197  |                          5.36809 |
| GBPUSD   |        1.5 |    0.984252 |                          5.37147 |
| GBPUSD   |        2   |    0.98597  |                          5.38001 |
| USDCAD   |        0.5 |    0.950371 |                          3.81987 |
| USDCAD   |        0.8 |    0.978957 |                          3.91423 |
| USDCAD   |        1   |    0.984573 |                          3.92441 |
| USDCAD   |        1.2 |    0.986353 |                          3.92683 |
| USDCAD   |        1.5 |    0.98807  |                          3.92838 |
| USDCAD   |        2   |    0.989722 |                          3.93469 |
| USDCHF   |        0.5 |    0.948855 |                          3.71552 |
| USDCHF   |        0.8 |    0.963769 |                          3.76856 |
| USDCHF   |        1   |    0.968302 |                          3.7771  |
| USDCHF   |        1.2 |    0.970586 |                          3.76939 |
| USDCHF   |        1.5 |    0.973839 |                          3.77651 |
| USDCHF   |        2   |    0.975638 |                          3.78576 |
| USDJPY   |        0.5 |    0.91941  |                          7.00961 |
| USDJPY   |        0.8 |    0.96296  |                          7.29186 |
| USDJPY   |        1   |    0.975612 |                          7.38236 |
| USDJPY   |        1.2 |    0.979529 |                          7.40487 |
| USDJPY   |        1.5 |    0.985259 |                          7.45304 |
| USDJPY   |        2   |    0.988984 |                          7.46228 |

#### Plots
![stage_04_stop_limit_caps](../../figures/oco_bible/stage_04_stop_limit_caps.png)
![stage_04_execution_policy_bands](../../figures/oco_bible/stage_04_execution_policy_bands.png)

#### Policy Status
| symbol   |   metrics_total |   green_metric_count |   amber_metric_count |   red_metric_count | worst_band   | recommended_action_code   | recommended_action_summary                                       | red_metrics   | amber_metrics                |
|:---------|----------------:|---------------------:|---------------------:|-------------------:|:-------------|:--------------------------|:-----------------------------------------------------------------|:--------------|:-----------------------------|
| AUDUSD   |               5 |                    4 |                    1 |                  0 | amber        | A1_RECALIBRATE_CAP        | execution erosion elevated; recalibrate cap/slippage assumptions |               | erosion_spread_fee_plus_slip |
| EURUSD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only                     |               |                              |
| GBPUSD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only                     |               |                              |
| USDCAD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only                     |               |                              |
| USDCHF   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only                     |               |                              |
| USDJPY   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only                     |               |                              |

- policy_csv: `data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv`

#### Policy Metric Mapping (Detail)
| symbol   | metric_id                         |   metric_value | band   | action_code        | green_threshold   | amber_threshold   |
|:---------|:----------------------------------|---------------:|:-------|:-------------------|:------------------|:------------------|
| EURUSD   | E11_session_overshoot_dispersion  |      0.377896  | green  | A0_MONITOR         | <= 1.0000         | <= 1.3000         |
| EURUSD   | E12_cap_plateau_width_pips        |      1.5       | green  | A0_MONITOR         | >= 0.5000         | >= 0.3000         |
| EURUSD   | E13_nonfill_opportunity_cost_pips |      0.101956  | green  | A0_MONITOR         | <= 0.2000         | <= 0.3500         |
| EURUSD   | erosion_spread_fee_plus_slip      |     -0.933617  | green  | A0_MONITOR         | <= 0.3000         | <= 0.5000         |
| EURUSD   | tick_overshoot_p95_pips           |      0.4       | green  | A0_MONITOR         | <= 0.7000         | <= 1.0000         |
| GBPUSD   | E11_session_overshoot_dispersion  |      0.0973022 | green  | A0_MONITOR         | <= 1.0000         | <= 1.3000         |
| GBPUSD   | E12_cap_plateau_width_pips        |      1.5       | green  | A0_MONITOR         | >= 0.5000         | >= 0.3000         |
| GBPUSD   | E13_nonfill_opportunity_cost_pips |      0.105239  | green  | A0_MONITOR         | <= 0.2000         | <= 0.3500         |
| GBPUSD   | erosion_spread_fee_plus_slip      |     -1.34823   | green  | A0_MONITOR         | <= 0.3000         | <= 0.5000         |
| GBPUSD   | tick_overshoot_p95_pips           |      0.4       | green  | A0_MONITOR         | <= 0.7000         | <= 1.0000         |
| AUDUSD   | E11_session_overshoot_dispersion  |      0.17529   | green  | A0_MONITOR         | <= 1.0000         | <= 1.3000         |
| AUDUSD   | E12_cap_plateau_width_pips        |      1.5       | green  | A0_MONITOR         | >= 0.5000         | >= 0.3000         |
| AUDUSD   | E13_nonfill_opportunity_cost_pips |      0.062335  | green  | A0_MONITOR         | <= 0.2000         | <= 0.3500         |
| AUDUSD   | erosion_spread_fee_plus_slip      |      0.46048   | amber  | A1_RECALIBRATE_CAP | <= 0.3000         | <= 0.5000         |
| AUDUSD   | tick_overshoot_p95_pips           |      0.4       | green  | A0_MONITOR         | <= 0.7000         | <= 1.0000         |
| USDJPY   | E11_session_overshoot_dispersion  |      0.253072  | green  | A0_MONITOR         | <= 1.0000         | <= 1.3000         |
| USDJPY   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR         | >= 0.5000         | >= 0.3000         |
| USDJPY   | E13_nonfill_opportunity_cost_pips |      0.182184  | green  | A0_MONITOR         | <= 0.2000         | <= 0.3500         |
| USDJPY   | erosion_spread_fee_plus_slip      |     -3.4305    | green  | A0_MONITOR         | <= 0.3000         | <= 0.5000         |
| USDJPY   | tick_overshoot_p95_pips           |      0.4       | green  | A0_MONITOR         | <= 0.7000         | <= 1.0000         |
| USDCHF   | E11_session_overshoot_dispersion  |      0.196247  | green  | A0_MONITOR         | <= 1.0000         | <= 1.3000         |
| USDCHF   | E12_cap_plateau_width_pips        |      1.5       | green  | A0_MONITOR         | >= 0.5000         | >= 0.3000         |
| USDCHF   | E13_nonfill_opportunity_cost_pips |      0.0872835 | green  | A0_MONITOR         | <= 0.2000         | <= 0.3500         |
| USDCHF   | erosion_spread_fee_plus_slip      |      0.246025  | green  | A0_MONITOR         | <= 0.3000         | <= 0.5000         |
| USDCHF   | tick_overshoot_p95_pips           |      0.4       | green  | A0_MONITOR         | <= 0.7000         | <= 1.0000         |
| USDCAD   | E11_session_overshoot_dispersion  |      0.305139  | green  | A0_MONITOR         | <= 1.0000         | <= 1.3000         |
| USDCAD   | E12_cap_plateau_width_pips        |      1.5       | green  | A0_MONITOR         | >= 0.5000         | >= 0.3000         |
| USDCAD   | E13_nonfill_opportunity_cost_pips |      0.100596  | green  | A0_MONITOR         | <= 0.2000         | <= 0.3500         |
| USDCAD   | erosion_spread_fee_plus_slip      |      0.0970905 | green  | A0_MONITOR         | <= 0.3000         | <= 0.5000         |
| USDCAD   | tick_overshoot_p95_pips           |      0.4       | green  | A0_MONITOR         | <= 0.7000         | <= 1.0000         |

#### Session Rolling Cap Policy
| symbol   | session_bucket   |   lookback_days |   cap_quantile |   cap_pips |   rows_used |   session_cap_rows |   global_cap_rows |   fallback_rows |
|:---------|:-----------------|----------------:|---------------:|-----------:|------------:|-------------------:|------------------:|----------------:|
| EURUSD   | ASIA             |              20 |            0.9 |       0.2  |       25597 |              25397 |               128 |              72 |
| EURUSD   | LATE             |              20 |            0.9 |       0.2  |        4121 |               2450 |              1671 |               0 |
| EURUSD   | LONDON           |              20 |            0.9 |       0.4  |       29655 |              29455 |                72 |             128 |
| EURUSD   | NY               |              20 |            0.9 |       0.2  |       54462 |              54262 |               200 |               0 |
| GBPUSD   | ASIA             |              20 |            0.9 |       0.3  |       30600 |              30400 |               162 |              38 |
| GBPUSD   | LATE             |              20 |            0.9 |       0.3  |        2289 |                692 |              1597 |               0 |
| GBPUSD   | LONDON           |              20 |            0.9 |       0.3  |       40655 |              40455 |               121 |              79 |
| GBPUSD   | NY               |              20 |            0.9 |       0.3  |       63356 |              63156 |               117 |              83 |
| AUDUSD   | ASIA             |              20 |            0.9 |       0.2  |       10886 |              10383 |               454 |              49 |
| AUDUSD   | LATE             |              20 |            0.9 |       0.3  |        1584 |                214 |              1362 |               8 |
| AUDUSD   | LONDON           |              20 |            0.9 |       0.5  |        6025 |               4272 |              1708 |              45 |
| AUDUSD   | NY               |              20 |            0.9 |       0.2  |       11910 |              11368 |               444 |              98 |
| USDJPY   | ASIA             |              20 |            0.9 |       0.4  |       98929 |              98729 |               128 |              72 |
| USDJPY   | LATE             |              20 |            0.9 |       0.4  |       15895 |              15695 |               124 |              76 |
| USDJPY   | LONDON           |              20 |            0.9 |       0.5  |       55833 |              55633 |               148 |              52 |
| USDJPY   | NY               |              20 |            0.9 |       0.4  |       76045 |              75845 |               200 |               0 |
| USDCHF   | ASIA             |              20 |            0.9 |       0.2  |        7196 |               5586 |              1590 |              20 |
| USDCHF   | LATE             |              20 |            0.9 |       0.2  |         717 |                  0 |               717 |               0 |
| USDCHF   | LONDON           |              20 |            0.9 |       0.27 |        8886 |               8104 |               707 |              75 |
| USDCHF   | NY               |              20 |            0.9 |       0.2  |       11455 |              10853 |               497 |             105 |
| USDCAD   | ASIA             |              20 |            0.9 |       0.2  |        7821 |               6463 |              1311 |              47 |
| USDCAD   | LATE             |              20 |            0.9 |       0.2  |        1214 |                115 |              1090 |               9 |
| USDCAD   | LONDON           |              20 |            0.9 |       0.2  |       10919 |              10164 |               686 |              69 |
| USDCAD   | NY               |              20 |            0.9 |       0.2  |       26819 |              26619 |               125 |              75 |

### Auto Snapshot - Stage 04

- generated_at: `2026-03-23 20:05:07 UTC`
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.
- E11-E13 are informational execution diagnostics: session dispersion, plateau width, and non-fill opportunity cost.
- Policy status artifact: data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv
- Session cap artifact: data/analysis/tick_opportunity_mining/stage04_cap_policy_by_session.csv

#### Key Results
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_p95_pips |   e11_session_overshoot_dispersion |   e12_cap_plateau_width_pips |   e13_nonfill_opportunity_cost_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|--------------------------:|-----------------------------------:|-----------------------------:|------------------------------------:|
| EURUSD   | 441961 |           0.951084 |               1.43092  |                   0.803633 |                      0.9  |                           0.605618 |                          1.2 |                           0.117218  |
| GBPUSD   | 431157 |           0.887929 |               0.972264 |                   2.65752  |                     18.42 |                           0.666546 |                          1.2 |                           0.0900974 |
| AUDUSD   | 385590 |           0.905892 |               0.560447 |                   1.24815  |                      6.7  |                           0.873188 |                          1.5 |                           0.0696582 |
| USDJPY   | 471371 |           0.898774 |               1.36908  |                   2.69543  |                     17.7  |                           0.29756  |                          1.2 |                           0.136558  |
| USDCHF   | 348977 |           0.908808 |               0.804334 |                   1.23741  |                      4.6  |                           0.31753  |                          1.2 |                           0.0932714 |
| USDCAD   | 501026 |           0.923313 |               1.05289  |                   1.51483  |                      5.9  |                           1.07349  |                          1   |                           0.144717  |

#### Interpretation Notes
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.

#### Action Trigger Summary
| symbol   | metric_id                         | band   | severity   | action_code           | action_summary         | owner     |
|:---------|:----------------------------------|:-------|:-----------|:----------------------|:-----------------------|:----------|
| AUDUSD   | E11_session_overshoot_dispersion  | red    | high       | A3_HALT_AND_REMEDIATE | escalate and remediate | execution |
| AUDUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR            | within policy band     | execution |
| AUDUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR            | within policy band     | execution |
| EURUSD   | E11_session_overshoot_dispersion  | red    | high       | A3_HALT_AND_REMEDIATE | escalate and remediate | execution |
| EURUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR            | within policy band     | execution |
| EURUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR            | within policy band     | execution |
| GBPUSD   | E11_session_overshoot_dispersion  | red    | high       | A3_HALT_AND_REMEDIATE | escalate and remediate | execution |
| GBPUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR            | within policy band     | execution |
| GBPUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR            | within policy band     | execution |
| USDCAD   | E11_session_overshoot_dispersion  | red    | high       | A3_HALT_AND_REMEDIATE | escalate and remediate | execution |
| USDCAD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR            | within policy band     | execution |
| USDCAD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR            | within policy band     | execution |

#### Details
| symbol   |   cap_pips |   fill_rate |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|---------------------------------:|
| AUDUSD   |        0.5 |    0.812246 |                         0.370272 |
| AUDUSD   |        0.8 |    0.828681 |                         0.384038 |
| AUDUSD   |        1   |    0.834085 |                         0.382678 |
| AUDUSD   |        1.2 |    0.836964 |                         0.385946 |
| AUDUSD   |        1.5 |    0.840893 |                         0.381779 |
| AUDUSD   |        2   |    0.844163 |                         0.382123 |
| EURUSD   |        0.5 |    0.861395 |                         1.05088  |
| EURUSD   |        0.8 |    0.895308 |                         1.10657  |
| EURUSD   |        1   |    0.906478 |                         1.11781  |
| EURUSD   |        1.2 |    0.911035 |                         1.13289  |
| EURUSD   |        1.5 |    0.915336 |                         1.15045  |
| EURUSD   |        2   |    0.919165 |                         1.15647  |
| GBPUSD   |        0.5 |    0.751912 |                         0.645604 |
| GBPUSD   |        0.8 |    0.781643 |                         0.67556  |
| GBPUSD   |        1   |    0.788367 |                         0.686295 |
| GBPUSD   |        1.2 |    0.790974 |                         0.686633 |
| GBPUSD   |        1.5 |    0.7943   |                         0.686953 |
| GBPUSD   |        2   |    0.79764  |                         0.686291 |
| USDCAD   |        0.5 |    0.767717 |                         0.636381 |
| USDCAD   |        0.8 |    0.818101 |                         0.693811 |
| USDCAD   |        1   |    0.834076 |                         0.714895 |
| USDCAD   |        1.2 |    0.841874 |                         0.721627 |
| USDCAD   |        1.5 |    0.850359 |                         0.742582 |
| USDCAD   |        2   |    0.859397 |                         0.752358 |
| USDCHF   |        0.5 |    0.798282 |                         0.548927 |
| USDCHF   |        0.8 |    0.82263  |                         0.575122 |
| USDCHF   |        1   |    0.829714 |                         0.578056 |
| USDCHF   |        1.2 |    0.834021 |                         0.580316 |
| USDCHF   |        1.5 |    0.840308 |                         0.582346 |
| USDCHF   |        2   |    0.845832 |                         0.578921 |
| USDJPY   |        0.5 |    0.745258 |                         0.850534 |
| USDJPY   |        0.8 |    0.785814 |                         0.897781 |
| USDJPY   |        1   |    0.79916  |                         0.918011 |
| USDJPY   |        1.2 |    0.80373  |                         0.923116 |
| USDJPY   |        1.5 |    0.810504 |                         0.935053 |
| USDJPY   |        2   |    0.814715 |                         0.940752 |

#### Plots
![stage_04_stop_limit_caps](../../figures/oco_bible/stage_04_stop_limit_caps.png)
![stage_04_execution_policy_bands](../../figures/oco_bible/stage_04_execution_policy_bands.png)

#### Execution Risk Pre-Live
| symbol   |   checks_total |   checks_failed |   high_critical_failed |   e02_min_month_fill_rate |   e03_tail_above_cap |   e10_lb95_month_signal_net |
|:---------|---------------:|----------------:|-----------------------:|--------------------------:|---------------------:|----------------------------:|
| EURUSD   |             10 |               3 |                      3 |                 0.0305547 |            0.0421086 |                    0.803102 |
| GBPUSD   |             10 |               4 |                      4 |                 0.0278215 |            0.109193  |                    0.530715 |
| AUDUSD   |             10 |               4 |                      4 |                 0.0399464 |            0.0760887 |                    0.169848 |
| USDJPY   |             10 |               4 |                      4 |                 0.0282973 |            0.105749  |                    0.704148 |
| USDCHF   |             10 |               4 |                      4 |                 0.0454435 |            0.0822915 |                    0.225814 |
| USDCAD   |             10 |               4 |                      4 |                 0.0481381 |            0.0882029 |                    0.369575 |

#### Policy Status
| symbol   |   metrics_total |   green_metric_count |   amber_metric_count |   red_metric_count | worst_band   | recommended_action_code   | recommended_action_summary                                       | red_metrics             | amber_metrics                                                 |
|:---------|----------------:|---------------------:|---------------------:|-------------------:|:-------------|:--------------------------|:-----------------------------------------------------------------|:------------------------|:--------------------------------------------------------------|
| AUDUSD   |               5 |                    4 |                    0 |                  1 | red          | A3_HALT_RECALIBRATE       | overshoot tail unsafe; halt and revalidate execution assumptions | tick_overshoot_p95_pips |                                                               |
| EURUSD   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor         |                         | tick_overshoot_p95_pips                                       |
| GBPUSD   |               5 |                    4 |                    0 |                  1 | red          | A3_HALT_RECALIBRATE       | overshoot tail unsafe; halt and revalidate execution assumptions | tick_overshoot_p95_pips |                                                               |
| USDCAD   |               5 |                    2 |                    2 |                  1 | red          | A3_HALT_RECALIBRATE       | overshoot tail unsafe; halt and revalidate execution assumptions | tick_overshoot_p95_pips | E11_session_overshoot_dispersion,erosion_spread_fee_plus_slip |
| USDCHF   |               5 |                    4 |                    0 |                  1 | red          | A3_HALT_RECALIBRATE       | overshoot tail unsafe; halt and revalidate execution assumptions | tick_overshoot_p95_pips |                                                               |
| USDJPY   |               5 |                    3 |                    1 |                  1 | red          | A3_HALT_RECALIBRATE       | overshoot tail unsafe; halt and revalidate execution assumptions | tick_overshoot_p95_pips | erosion_spread_fee_plus_slip                                  |

- policy_csv: `data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv`

#### Policy Metric Mapping (Detail)
| symbol   | metric_id                         |   metric_value | band   | action_code         | green_threshold   | amber_threshold   |
|:---------|:----------------------------------|---------------:|:-------|:--------------------|:------------------|:------------------|
| EURUSD   | E11_session_overshoot_dispersion  |      0.605618  | green  | A0_MONITOR          | <= 1.0000         | <= 1.3000         |
| EURUSD   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| EURUSD   | E13_nonfill_opportunity_cost_pips |      0.117218  | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| EURUSD   | erosion_spread_fee_plus_slip      |      0.274449  | green  | A0_MONITOR          | <= 0.3000         | <= 0.5000         |
| EURUSD   | tick_overshoot_p95_pips           |      0.9       | amber  | A2_SESSION_GUARD    | <= 0.7000         | <= 1.0000         |
| GBPUSD   | E11_session_overshoot_dispersion  |      0.666546  | green  | A0_MONITOR          | <= 1.0000         | <= 1.3000         |
| GBPUSD   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| GBPUSD   | E13_nonfill_opportunity_cost_pips |      0.0900974 | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| GBPUSD   | erosion_spread_fee_plus_slip      |      0.28531   | green  | A0_MONITOR          | <= 0.3000         | <= 0.5000         |
| GBPUSD   | tick_overshoot_p95_pips           |     18.42      | red    | A3_HALT_RECALIBRATE | <= 0.7000         | <= 1.0000         |
| AUDUSD   | E11_session_overshoot_dispersion  |      0.873188  | green  | A0_MONITOR          | <= 1.0000         | <= 1.3000         |
| AUDUSD   | E12_cap_plateau_width_pips        |      1.5       | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| AUDUSD   | E13_nonfill_opportunity_cost_pips |      0.0696582 | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| AUDUSD   | erosion_spread_fee_plus_slip      |      0.174501  | green  | A0_MONITOR          | <= 0.3000         | <= 0.5000         |
| AUDUSD   | tick_overshoot_p95_pips           |      6.7       | red    | A3_HALT_RECALIBRATE | <= 0.7000         | <= 1.0000         |
| USDJPY   | E11_session_overshoot_dispersion  |      0.29756   | green  | A0_MONITOR          | <= 1.0000         | <= 1.3000         |
| USDJPY   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| USDJPY   | E13_nonfill_opportunity_cost_pips |      0.136558  | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| USDJPY   | erosion_spread_fee_plus_slip      |      0.428332  | amber  | A1_RECALIBRATE_CAP  | <= 0.3000         | <= 0.5000         |
| USDJPY   | tick_overshoot_p95_pips           |     17.7       | red    | A3_HALT_RECALIBRATE | <= 0.7000         | <= 1.0000         |
| USDCHF   | E11_session_overshoot_dispersion  |      0.31753   | green  | A0_MONITOR          | <= 1.0000         | <= 1.3000         |
| USDCHF   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| USDCHF   | E13_nonfill_opportunity_cost_pips |      0.0932714 | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| USDCHF   | erosion_spread_fee_plus_slip      |      0.221989  | green  | A0_MONITOR          | <= 0.3000         | <= 0.5000         |
| USDCHF   | tick_overshoot_p95_pips           |      4.6       | red    | A3_HALT_RECALIBRATE | <= 0.7000         | <= 1.0000         |
| USDCAD   | E11_session_overshoot_dispersion  |      1.07349   | amber  | A2_SESSION_GUARD    | <= 1.0000         | <= 1.3000         |
| USDCAD   | E12_cap_plateau_width_pips        |      1         | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| USDCAD   | E13_nonfill_opportunity_cost_pips |      0.144717  | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| USDCAD   | erosion_spread_fee_plus_slip      |      0.300534  | amber  | A1_RECALIBRATE_CAP  | <= 0.3000         | <= 0.5000         |
| USDCAD   | tick_overshoot_p95_pips           |      5.9       | red    | A3_HALT_RECALIBRATE | <= 0.7000         | <= 1.0000         |

#### Session Rolling Cap Policy
| symbol   | session_bucket   |   lookback_days |   cap_quantile |   cap_pips |   rows_used |   session_cap_rows |   global_cap_rows |   fallback_rows |
|:---------|:-----------------|----------------:|---------------:|-----------:|------------:|-------------------:|------------------:|----------------:|
| EURUSD   | ASIA             |              20 |            0.9 |      31.6  |      108236 |             108036 |                11 |             189 |
| EURUSD   | LATE             |              20 |            0.9 |      39.6  |       21832 |              20843 |               985 |               4 |
| EURUSD   | LONDON           |              20 |            0.9 |      50.6  |       99485 |              99285 |               200 |               0 |
| EURUSD   | NY               |              20 |            0.9 |      22.45 |      190495 |             190295 |               200 |               0 |
| GBPUSD   | ASIA             |              20 |            0.9 |      31.8  |       74165 |              73965 |               110 |              90 |
| GBPUSD   | LATE             |              20 |            0.9 |      50.9  |       12891 |              12080 |               811 |               0 |
| GBPUSD   | LONDON           |              20 |            0.9 |      62.8  |      136152 |             135952 |                90 |             110 |
| GBPUSD   | NY               |              20 |            0.9 |      34.8  |      159345 |             159145 |               200 |               0 |
| AUDUSD   | ASIA             |              20 |            0.9 |      28    |      144913 |             144713 |                60 |             140 |
| AUDUSD   | LATE             |              20 |            0.9 |      39    |       13172 |              12140 |               972 |              60 |
| AUDUSD   | LONDON           |              20 |            0.9 |      31.4  |       56849 |              56649 |               200 |               0 |
| AUDUSD   | NY               |              20 |            0.9 |      42.1  |      134074 |             133874 |               200 |               0 |
| USDJPY   | ASIA             |              20 |            0.9 |      66.6  |      229708 |             229508 |                23 |             177 |
| USDJPY   | LATE             |              20 |            0.9 |      77    |       26113 |              25913 |               177 |              23 |
| USDJPY   | LONDON           |              20 |            0.9 |      92.2  |       78468 |              78268 |               200 |               0 |
| USDJPY   | NY               |              20 |            0.9 |      53.3  |       89003 |              88803 |               200 |               0 |
| USDCHF   | ASIA             |              20 |            0.9 |      17.5  |       69045 |              68845 |                50 |             150 |
| USDCHF   | LATE             |              20 |            0.9 |      22.4  |       10822 |               9582 |              1192 |              48 |
| USDCHF   | LONDON           |              20 |            0.9 |      44.8  |       94808 |              94608 |               198 |               2 |
| USDCHF   | NY               |              20 |            0.9 |      17    |      142187 |             141987 |               200 |               0 |
| USDCAD   | ASIA             |              20 |            0.9 |      18.08 |       90773 |              90573 |               155 |              45 |
| USDCAD   | LATE             |              20 |            0.9 |      68.56 |       18107 |              16824 |              1128 |             155 |
| USDCAD   | LONDON           |              20 |            0.9 |      68.7  |       77528 |              77328 |               200 |               0 |
| USDCAD   | NY               |              20 |            0.9 |      21.9  |      275958 |             275758 |               200 |               0 |

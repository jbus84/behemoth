### Auto Snapshot - Stage 04

- generated_at: `2026-02-27 18:50:29 UTC`
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.
- E11-E13 are informational execution diagnostics: session dispersion, plateau width, and non-fill opportunity cost.
- Policy status artifact: data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv
- Session cap artifact: data/analysis/tick_opportunity_mining/stage04_cap_policy_by_session.csv

#### Key Results
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_p95_pips |   e11_session_overshoot_dispersion |   e12_cap_plateau_width_pips |   e13_nonfill_opportunity_cost_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|--------------------------:|-----------------------------------:|-----------------------------:|------------------------------------:|
| EURUSD   |  59955 |           1        |                1.08782 |                   0.142048 |                       0.6 |                           0.223359 |                          1   |                            0.12845  |
| GBPUSD   |  70579 |           0.999972 |                1.0077  |                   0.136394 |                       0.5 |                           0.307728 |                          1.5 |                            0.112243 |
| USDJPY   |  77785 |           0.999974 |                1.37716 |                   0.230743 |                       0.7 |                           0.1544   |                          1.2 |                            0.192022 |

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
| EURUSD   |        0.5 |    0.938154 |                         0.824463 |
| EURUSD   |        0.8 |    0.972196 |                         0.873018 |
| EURUSD   |        1   |    0.984288 |                         0.896848 |
| EURUSD   |        1.2 |    0.987808 |                         0.904805 |
| EURUSD   |        1.5 |    0.992878 |                         0.919832 |
| EURUSD   |        2   |    0.996497 |                         0.924965 |
| GBPUSD   |        0.5 |    0.952677 |                         0.833203 |
| GBPUSD   |        0.8 |    0.982559 |                         0.85246  |
| GBPUSD   |        1   |    0.990096 |                         0.865807 |
| GBPUSD   |        1.2 |    0.991952 |                         0.86801  |
| GBPUSD   |        1.5 |    0.994177 |                         0.86661  |
| GBPUSD   |        2   |    0.996189 |                         0.867322 |
| USDJPY   |        0.5 |    0.916359 |                         1.05383  |
| USDJPY   |        0.8 |    0.962409 |                         1.09799  |
| USDJPY   |        1   |    0.976499 |                         1.11894  |
| USDJPY   |        1.2 |    0.980857 |                         1.12001  |
| USDJPY   |        1.5 |    0.988211 |                         1.14471  |
| USDJPY   |        2   |    0.992441 |                         1.15173  |

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
| symbol   |   metrics_total |   green_metric_count |   amber_metric_count |   red_metric_count | worst_band   | recommended_action_code   | recommended_action_summary                               | red_metrics   | amber_metrics           |
|:---------|----------------:|---------------------:|---------------------:|-------------------:|:-------------|:--------------------------|:---------------------------------------------------------|:--------------|:------------------------|
| EURUSD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only             |               |                         |
| GBPUSD   |               5 |                    5 |                    0 |                  0 | green        | A0_MONITOR                | within execution policy limits; monitor only             |               |                         |
| USDJPY   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor |               | tick_overshoot_p95_pips |

- policy_csv: `data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv`

#### Policy Metric Mapping (Detail)
| symbol   | metric_id                         |   metric_value | band   | action_code      | green_threshold   | amber_threshold   |
|:---------|:----------------------------------|---------------:|:-------|:-----------------|:------------------|:------------------|
| EURUSD   | E11_session_overshoot_dispersion  |       0.223359 | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| EURUSD   | E12_cap_plateau_width_pips        |       1        | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| EURUSD   | E13_nonfill_opportunity_cost_pips |       0.12845  | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| EURUSD   | erosion_spread_fee_plus_slip      |       0.16285  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| EURUSD   | tick_overshoot_p95_pips           |       0.6      | green  | A0_MONITOR       | <= 0.7000         | <= 1.0000         |
| GBPUSD   | E11_session_overshoot_dispersion  |       0.307728 | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| GBPUSD   | E12_cap_plateau_width_pips        |       1.5      | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| GBPUSD   | E13_nonfill_opportunity_cost_pips |       0.112243 | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| GBPUSD   | erosion_spread_fee_plus_slip      |       0.13969  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| GBPUSD   | tick_overshoot_p95_pips           |       0.5      | green  | A0_MONITOR       | <= 0.7000         | <= 1.0000         |
| USDJPY   | E11_session_overshoot_dispersion  |       0.1544   | green  | A0_MONITOR       | <= 1.0000         | <= 1.3000         |
| USDJPY   | E12_cap_plateau_width_pips        |       1.2      | green  | A0_MONITOR       | >= 0.5000         | >= 0.3000         |
| USDJPY   | E13_nonfill_opportunity_cost_pips |       0.192022 | green  | A0_MONITOR       | <= 0.2000         | <= 0.3500         |
| USDJPY   | erosion_spread_fee_plus_slip      |       0.22543  | green  | A0_MONITOR       | <= 0.3000         | <= 0.5000         |
| USDJPY   | tick_overshoot_p95_pips           |       0.7      | amber  | A2_SESSION_GUARD | <= 0.7000         | <= 1.0000         |

#### Session Rolling Cap Policy
| symbol   | session_bucket   |   lookback_days |   cap_quantile |   cap_pips |   rows_used |   session_cap_rows |   global_cap_rows |   fallback_rows |
|:---------|:-----------------|----------------:|---------------:|-----------:|------------:|-------------------:|------------------:|----------------:|
| EURUSD   | ASIA             |              20 |            0.9 |        0.2 |       22526 |              22326 |                90 |             110 |
| EURUSD   | LATE             |              20 |            0.9 |        0.3 |        2034 |                955 |              1079 |               0 |
| EURUSD   | LONDON           |              20 |            0.9 |        0.2 |       22976 |              22776 |               135 |              65 |
| EURUSD   | NY               |              20 |            0.9 |        0.2 |       12363 |              11935 |               403 |              25 |
| GBPUSD   | ASIA             |              20 |            0.9 |        0.3 |       30437 |              30237 |                14 |             186 |
| GBPUSD   | LATE             |              20 |            0.9 |        0.4 |         682 |                131 |               551 |               0 |
| GBPUSD   | LONDON           |              20 |            0.9 |        0.3 |       32672 |              32472 |               186 |              14 |
| GBPUSD   | NY               |              20 |            0.9 |        0.3 |        6724 |               5868 |               856 |               0 |
| USDJPY   | ASIA             |              20 |            0.9 |        0.4 |       31168 |              30968 |                95 |             105 |
| USDJPY   | LATE             |              20 |            0.9 |        0.5 |        3901 |               3442 |               459 |               0 |
| USDJPY   | LONDON           |              20 |            0.9 |        0.4 |       23284 |              23084 |               105 |              95 |
| USDJPY   | NY               |              20 |            0.9 |        0.6 |       19352 |              19152 |               200 |               0 |

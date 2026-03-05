### Auto Snapshot - Stage 08

- generated_at: `2026-03-05 14:41:51 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |   6715 |       11 |           2.61078 |                     2.5027   |                11 |
| GBPUSD   |        0.9 |   6978 |        6 |           2.66873 |                     2.57413  |                 6 |
| AUDUSD   |        0.9 |   4227 |        6 |           1.04687 |                     0.952247 |                 6 |
| USDJPY   |        0.9 |   8186 |        6 |           3.52446 |                     3.41566  |                 6 |
| USDCHF   |        0.9 |   4170 |        6 |           1.4852  |                     1.37476  |                 6 |
| USDCAD   |        0.9 |   3574 |        6 |           1.52731 |                     1.41111  |                 6 |

#### Interpretation Notes
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.

#### Action Trigger Summary
| symbol   | metric_id                     | band   | severity   | action_code   | action_summary     | owner   |
|:---------|:------------------------------|:-------|:-----------|:--------------|:-------------------|:--------|
| AUDUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR    | within policy band | risk    |
| AUDUSD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR    | within policy band | risk    |
| AUDUSD   | T03_post_worst_month_recovery | amber  | medium     | A1_REVIEW     | review and monitor | risk    |
| EURUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR    | within policy band | risk    |
| EURUSD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR    | within policy band | risk    |
| EURUSD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR    | within policy band | risk    |
| GBPUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR    | within policy band | risk    |
| GBPUSD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR    | within policy band | risk    |
| GBPUSD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR    | within policy band | risk    |
| USDCAD   | T01_stress_elasticity         | green  | info       | A0_MONITOR    | within policy band | risk    |
| USDCAD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR    | within policy band | risk    |
| USDCAD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR    | within policy band | risk    |

#### Details
| symbol   |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   t01_stress_elasticity |   t02_first_negative_costplus |   t04_max_survivable_cost_lb95_trade |   t03_post_worst_month_recovery |   lb95_trade_mean_net_pips_costplus_0.10 |   lb95_trade_mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.30 |   lb95_trade_mean_net_pips_costplus_0.50 |
|:---------|------------------------:|--------------------:|----------------:|------------------------:|------------------------------:|-------------------------------------:|--------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|
| EURUSD   |                       0 |                   0 |               0 |                      -1 |                          2    |                             2        |                        1.6805   |                                 2.4017   |                                  2.30075 |                                 2.20463  |                                 2.00484  |
| GBPUSD   |                       0 |                   0 |               0 |                      -1 |                          2    |                             2        |                        1.08338  |                                 2.47431  |                                  2.37179 |                                 2.2695   |                                 2.06504  |
| AUDUSD   |                       0 |                   0 |               0 |                      -1 |                          1.25 |                             0.952033 |                        0.529206 |                                 0.858455 |                                  0.75712 |                                 0.653463 |                                 0.454145 |
| USDJPY   |                       0 |                   0 |               0 |                      -1 |                          2    |                             2        |                        0.919414 |                                 3.31926  |                                  3.21768 |                                 3.11615  |                                 2.91812  |
| USDCHF   |                       0 |                   0 |               0 |                      -1 |                          1.5  |                             1.37441  |                        1.61149  |                                 1.27737  |                                  1.17565 |                                 1.07228  |                                 0.876746 |
| USDCAD   |                       0 |                   0 |               0 |                      -1 |                          1.75 |                             1.41285  |                        1.58167  |                                 1.31144  |                                  1.21327 |                                 1.1118   |                                 0.912847 |

#### Plots
![stage_08_robustness_lb95](../../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../../figures/oco_bible/stage_08_overfit_symbol_panel.png)

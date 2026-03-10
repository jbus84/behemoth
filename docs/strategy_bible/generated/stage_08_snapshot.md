### Auto Snapshot - Stage 08

- generated_at: `2026-03-10 10:13:11 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |   5934 |       10 |           2.83795 |                      2.72549 |                10 |
| GBPUSD   |        0.9 |  12161 |       11 |           2.77239 |                      2.69625 |                11 |
| AUDUSD   |        0.9 |   7789 |       11 |           1.6767  |                      1.59632 |                11 |
| USDJPY   |        0.9 |  13266 |       11 |           3.88653 |                      3.79579 |                11 |
| USDCHF   |        0.9 |  10408 |       11 |           2.15095 |                      2.07321 |                11 |
| USDCAD   |        0.9 |   7809 |       11 |           2.30917 |                      2.21911 |                11 |

#### Interpretation Notes
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.

#### Action Trigger Summary
| symbol   | metric_id                     | band   | severity   | action_code   | action_summary     | owner   |
|:---------|:------------------------------|:-------|:-----------|:--------------|:-------------------|:--------|
| AUDUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR    | within policy band | risk    |
| AUDUSD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR    | within policy band | risk    |
| AUDUSD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR    | within policy band | risk    |
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
| EURUSD   |             1.88738e-15 |         1.13243e-14 |     5.66214e-15 |                      -1 |                          2    |                              2       |                         1.29602 |                                  2.62152 |                                  2.5239  |                                  2.42593 |                                  2.22439 |
| GBPUSD   |             0           |         0           |     0           |                      -1 |                          2    |                              2       |                         1.10572 |                                  2.59791 |                                  2.50045 |                                  2.39667 |                                  2.20334 |
| AUDUSD   |             0           |         0           |     0           |                      -1 |                          1.75 |                              1.59776 |                         2.43772 |                                  1.49704 |                                  1.39533 |                                  1.29631 |                                  1.09853 |
| USDJPY   |             0           |         0           |     0           |                      -1 |                          2    |                              2       |                         1.13612 |                                  3.69815 |                                  3.59624 |                                  3.49552 |                                  3.29708 |
| USDCHF   |             4.32987e-14 |         2.59792e-13 |     2.59792e-13 |                      -1 |                          2    |                              2       |                         2.21997 |                                  1.97892 |                                  1.87454 |                                  1.77512 |                                  1.57802 |
| USDCAD   |             8.88178e-16 |         5.32907e-15 |     5.32907e-15 |                      -1 |                          2    |                              2       |                         2.9865  |                                  2.11745 |                                  2.01949 |                                  1.91395 |                                  1.71427 |

#### Plots
![stage_08_robustness_lb95](../../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../../figures/oco_bible/stage_08_overfit_symbol_panel.png)

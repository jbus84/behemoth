### Auto Snapshot - Stage 08

- generated_at: `2026-03-06 10:46:49 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |   6197 |       11 |           2.62325 |                      2.51145 |                11 |
| GBPUSD   |        0.9 |  12754 |       11 |           2.61462 |                      2.5427  |                11 |
| AUDUSD   |        0.9 |   8335 |       11 |           1.83642 |                      1.75361 |                11 |
| USDJPY   |        0.9 |  12137 |       11 |           4.04278 |                      3.95632 |                11 |
| USDCHF   |        0.9 |   9685 |       11 |           2.07737 |                      1.99965 |                11 |
| USDCAD   |        0.9 |   8460 |       11 |           2.16115 |                      2.07781 |                11 |

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
| EURUSD   |             0           |         0           |     0           |                      -1 |                             2 |                              2       |                         1.83081 |                                  2.41602 |                                  2.30598 |                                  2.2158  |                                  2.01409 |
| GBPUSD   |             0           |         0           |     0           |                      -1 |                             2 |                              2       |                         1.14889 |                                  2.44202 |                                  2.3457  |                                  2.24348 |                                  2.04344 |
| AUDUSD   |             0           |         0           |     0           |                      -1 |                             2 |                              1.74868 |                         1.79224 |                                  1.65448 |                                  1.55153 |                                  1.45145 |                                  1.24819 |
| USDJPY   |             0           |         0           |     0           |                      -1 |                             2 |                              2       |                         1.06499 |                                  3.84909 |                                  3.74821 |                                  3.65533 |                                  3.45139 |
| USDCHF   |             1.77636e-14 |         1.06581e-13 |     3.55271e-14 |                      -1 |                             2 |                              1.99821 |                         2.81389 |                                  1.89954 |                                  1.79756 |                                  1.69504 |                                  1.49976 |
| USDCAD   |             5.36238e-13 |         3.21743e-12 |     3.21743e-12 |                      -1 |                             2 |                              2       |                         3.62638 |                                  1.97144 |                                  1.87676 |                                  1.77839 |                                  1.57686 |

#### Plots
![stage_08_robustness_lb95](../../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../../figures/oco_bible/stage_08_overfit_symbol_panel.png)

### Auto Snapshot - Stage 08

- generated_at: `2026-03-30 10:10:58 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |   4267 |       10 |           2.55697 |                      2.42312 |                10 |
| GBPUSD   |        0.9 |   9776 |       11 |           2.66908 |                      2.58253 |                11 |
| AUDUSD   |        0.9 |   6102 |       10 |           1.60241 |                      1.51152 |                10 |
| USDJPY   |        0.9 |  10002 |       11 |           3.89593 |                      3.79905 |                11 |
| USDCHF   |        0.9 |   6782 |       11 |           1.83285 |                      1.748   |                11 |
| USDCAD   |        0.9 |   7942 |       11 |           2.04433 |                      1.95503 |                11 |

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
| GBPUSD   | T03_post_worst_month_recovery | amber  | medium     | A1_REVIEW     | review and monitor | risk    |
| USDCAD   | T01_stress_elasticity         | green  | info       | A0_MONITOR    | within policy band | risk    |
| USDCAD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR    | within policy band | risk    |
| USDCAD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR    | within policy band | risk    |

#### Details
| symbol   |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   t01_stress_elasticity |   t02_first_negative_costplus |   t04_max_survivable_cost_lb95_trade |   t03_post_worst_month_recovery |   lb95_trade_mean_net_pips_costplus_0.10 |   lb95_trade_mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.30 |   lb95_trade_mean_net_pips_costplus_0.50 |
|:---------|------------------------:|--------------------:|----------------:|------------------------:|------------------------------:|-------------------------------------:|--------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|
| EURUSD   |             1.62204e-13 |         9.73222e-13 |     2.30749e-13 |                      -1 |                          2    |                              2       |                         2.97078 |                                  2.33169 |                                  2.23077 |                                  2.12758 |                                  1.92353 |
| GBPUSD   |             0           |         0           |     0           |                      -1 |                          2    |                              2       |                         0.51401 |                                  2.48606 |                                  2.38786 |                                  2.28805 |                                  2.08465 |
| AUDUSD   |             6.95666e-13 |         4.17399e-12 |     1.39133e-12 |                      -1 |                          1.75 |                              1.51241 |                         1.53875 |                                  1.41331 |                                  1.31332 |                                  1.20679 |                                  1.01151 |
| USDJPY   |             0           |         0           |     0           |                      -1 |                          2    |                              2       |                         1.35218 |                                  3.7027  |                                  3.5985  |                                  3.49429 |                                  3.30007 |
| USDCHF   |             2.03171e-14 |         1.21902e-13 |     6.09512e-14 |                      -1 |                          2    |                              1.74068 |                         1.74994 |                                  1.6445  |                                  1.53811 |                                  1.44225 |                                  1.24097 |
| USDCAD   |             1.02516e-11 |         6.15095e-11 |     1.23019e-11 |                      -1 |                          2    |                              1.9572  |                         1.3123  |                                  1.85645 |                                  1.75757 |                                  1.65324 |                                  1.45234 |

#### Plots
![stage_08_robustness_lb95](../../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../../figures/oco_bible/stage_08_overfit_symbol_panel.png)

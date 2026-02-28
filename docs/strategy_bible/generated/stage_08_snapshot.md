### Auto Snapshot - Stage 08

- generated_at: `2026-02-28 20:57:22 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |   4923 |        6 |          1.69669  |                     1.60064  |                 6 |
| GBPUSD   |        0.9 |   4427 |        9 |          0.808516 |                     0.696371 |                 9 |
| USDJPY   |        0.9 |   4939 |        9 |          1.40326  |                     1.25936  |                 9 |
| USDCHF   |        0.9 |   4173 |        6 |          1.54333  |                     1.43592  |                 6 |
| USDCAD   |        0.9 |   3951 |        6 |          1.28674  |                     1.18194  |                 6 |

#### Interpretation Notes
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.

#### Action Trigger Summary
| symbol   | metric_id                     | band   | severity   | action_code    | action_summary         | owner   |
|:---------|:------------------------------|:-------|:-----------|:---------------|:-----------------------|:--------|
| EURUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR     | within policy band     | risk    |
| EURUSD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR     | within policy band     | risk    |
| EURUSD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR     | within policy band     | risk    |
| GBPUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR     | within policy band     | risk    |
| GBPUSD   | T02_first_negative_costplus   | red    | high       | A2_RECALIBRATE | escalate and remediate | risk    |
| GBPUSD   | T03_post_worst_month_recovery | red    | high       | A2_RECALIBRATE | escalate and remediate | risk    |
| USDJPY   | T01_stress_elasticity         | green  | info       | A0_MONITOR     | within policy band     | risk    |
| USDJPY   | T02_first_negative_costplus   | red    | high       | A2_RECALIBRATE | escalate and remediate | risk    |
| USDJPY   | T03_post_worst_month_recovery | red    | high       | A2_RECALIBRATE | escalate and remediate | risk    |

#### Details
| symbol   |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   t01_stress_elasticity |   t02_first_negative_costplus |   t04_max_survivable_cost_lb95_trade |   t03_post_worst_month_recovery |   lb95_trade_mean_net_pips_costplus_0.10 |   lb95_trade_mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.30 |   lb95_trade_mean_net_pips_costplus_0.50 |
|:---------|------------------------:|--------------------:|----------------:|------------------------:|------------------------------:|-------------------------------------:|--------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|
| EURUSD   |             1.78644e-11 |         1.07186e-10 |     2.67966e-11 |                      -1 |                          1.75 |                              1.59871 |                        0.915934 |                                 1.49583  |                                 1.40248  |                                 1.29949  |                                 1.10089  |
| GBPUSD   |             0           |         0           |     0           |                      -1 |                          0.5  |                              0.5     |                      nan        |                                 0.594654 |                                 0.491428 |                                 0.391254 |                                 0.194756 |
| USDJPY   |             0           |         0           |     0           |                      -1 |                          0.5  |                              0.5     |                      nan        |                                 1.15762  |                                 1.05588  |                                 0.95754  |                                 0.761891 |
| USDCHF   |             0           |         0           |     0           |                      -1 |                          1.75 |                              1.43499 |                        1.03157  |                                 1.33558  |                                 1.22767  |                                 1.13335  |                                 0.932108 |
| USDCAD   |             4.66294e-15 |         2.79776e-14 |     1.39888e-14 |                      -1 |                          1.5  |                              1.17747 |                      nan        |                                 1.08193  |                                 0.979999 |                                 0.87936  |                                 0.681211 |

#### Plots
![stage_08_robustness_lb95](../../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../../figures/oco_bible/stage_08_overfit_symbol_panel.png)

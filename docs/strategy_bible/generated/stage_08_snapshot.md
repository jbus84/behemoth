### Auto Snapshot - Stage 08

- generated_at: `2026-04-12 17:21:09 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |   6430 |       12 |           7.67904 |                      7.44487 |                12 |
| GBPUSD   |        0.9 |   7191 |       12 |           7.75757 |                      7.50235 |                12 |
| AUDUSD   |        0.9 |   2388 |        7 |           5.47994 |                      5.12738 |                 7 |
| USDJPY   |        0.9 |   5205 |       12 |          11.1117  |                     10.7085  |                12 |
| USDCHF   |        0.9 |   1773 |        6 |           5.90609 |                      5.48371 |                 6 |
| USDCAD   |        0.9 |   4062 |       10 |           5.5452  |                      5.28134 |                10 |

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
| EURUSD   |                       0 |                   0 |               0 |                      -1 |                             2 |                                    2 |                        1.18376  |                                  7.34042 |                                  7.22717 |                                  7.13585 |                                  6.93726 |
| GBPUSD   |                       0 |                   0 |               0 |                      -1 |                             2 |                                    2 |                        1.31447  |                                  7.41184 |                                  7.32489 |                                  7.20847 |                                  7.01877 |
| AUDUSD   |                       0 |                   0 |               0 |                      -1 |                             2 |                                    2 |                        1.35771  |                                  5.03873 |                                  4.91895 |                                  4.83999 |                                  4.60913 |
| USDJPY   |                       0 |                   0 |               0 |                      -1 |                             2 |                                    2 |                        1.37464  |                                 10.6143  |                                 10.5115  |                                 10.4235  |                                 10.2234  |
| USDCHF   |                       0 |                   0 |               0 |                      -1 |                             2 |                                    2 |                        0.662697 |                                  5.36884 |                                  5.25772 |                                  5.16135 |                                  4.98345 |
| USDCAD   |                       0 |                   0 |               0 |                      -1 |                             2 |                                    2 |                        1.26487  |                                  5.17451 |                                  5.07508 |                                  4.98586 |                                  4.78172 |

#### Plots
![stage_08_robustness_lb95](../../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../../figures/oco_bible/stage_08_overfit_symbol_panel.png)

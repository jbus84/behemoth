### Auto Snapshot - Stage 08

- generated_at: `2026-02-27 18:50:29 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T03 summarize stress elasticity, negative-cost crossing, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |  59955 |        9 |           1.08782 |                     1.04912  |                 9 |
| GBPUSD   |        0.9 |  70579 |        9 |           1.0077  |                     0.973913 |                 9 |
| USDJPY   |        0.9 |  77785 |        9 |           1.37716 |                     1.33687  |                 9 |

#### Interpretation Notes
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.

#### Action Trigger Summary
| symbol   | metric_id                     | band   | severity   | action_code    | action_summary         | owner   |
|:---------|:------------------------------|:-------|:-----------|:---------------|:-----------------------|:--------|
| EURUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR     | within policy band     | risk    |
| EURUSD   | T02_first_negative_costplus   | red    | high       | A2_RECALIBRATE | escalate and remediate | risk    |
| EURUSD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR     | within policy band     | risk    |
| GBPUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR     | within policy band     | risk    |
| GBPUSD   | T02_first_negative_costplus   | red    | high       | A2_RECALIBRATE | escalate and remediate | risk    |
| GBPUSD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR     | within policy band     | risk    |
| USDJPY   | T01_stress_elasticity         | green  | info       | A0_MONITOR     | within policy band     | risk    |
| USDJPY   | T02_first_negative_costplus   | red    | high       | A2_RECALIBRATE | escalate and remediate | risk    |
| USDJPY   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR     | within policy band     | risk    |

#### Details
| symbol   |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   t01_stress_elasticity |   t02_first_negative_costplus |   t03_post_worst_month_recovery |   lb95_trade_mean_net_pips_costplus_0.10 |   lb95_trade_mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.30 |   lb95_trade_mean_net_pips_costplus_0.50 |
|:---------|------------------------:|--------------------:|----------------:|------------------------:|------------------------------:|--------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|
| EURUSD   |              2.4283e-09 |         1.45698e-08 |     2.91396e-09 |                      -1 |                           0.5 |                        0.921189 |                                 0.950816 |                                 0.847072 |                                 0.750602 |                                 0.54953  |
| GBPUSD   |              0          |         0           |     0           |                      -1 |                           0.5 |                        1.32015  |                                 0.874132 |                                 0.775311 |                                 0.673344 |                                 0.475306 |
| USDJPY   |              0          |         0           |     0           |                      -1 |                           0.5 |                        1.10927  |                                 1.23403  |                                 1.13592  |                                 1.03604  |                                 0.834248 |

#### Plots
![stage_08_robustness_lb95](../../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../../figures/oco_bible/stage_08_overfit_symbol_panel.png)

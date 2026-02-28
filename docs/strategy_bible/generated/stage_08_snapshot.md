### Auto Snapshot - Stage 08

- generated_at: `2026-02-28 14:54:13 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |  59955 |        9 |          1.08782  |                     1.04912  |                 9 |
| GBPUSD   |        0.9 |   4427 |        9 |          0.808516 |                     0.696371 |                 9 |
| USDJPY   |        0.9 |   4939 |        9 |          1.40326  |                     1.25936  |                 9 |
| USDCHF   |        0.9 | 366516 |        9 |          0.897313 |                     0.885075 |                 9 |

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
| GBPUSD   | T03_post_worst_month_recovery | gray   | high       | A9_DATA_GAP    | metric unavailable     | risk    |
| USDJPY   | T01_stress_elasticity         | green  | info       | A0_MONITOR     | within policy band     | risk    |
| USDJPY   | T02_first_negative_costplus   | red    | high       | A2_RECALIBRATE | escalate and remediate | risk    |
| USDJPY   | T03_post_worst_month_recovery | gray   | high       | A9_DATA_GAP    | metric unavailable     | risk    |

#### Details
| symbol   |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   t01_stress_elasticity |   t02_first_negative_costplus |   t04_max_survivable_cost_lb95_trade |   t03_post_worst_month_recovery |   lb95_trade_mean_net_pips_costplus_0.10 |   lb95_trade_mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.30 |   lb95_trade_mean_net_pips_costplus_0.50 |
|:---------|------------------------:|--------------------:|----------------:|------------------------:|------------------------------:|-------------------------------------:|--------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|
| EURUSD   |             2.4283e-09  |         1.45698e-08 |     2.91396e-09 |                      -1 |                           0.5 |                                  0.5 |                        0.915934 |                                 0.950816 |                                 0.847072 |                                 0.750602 |                                 0.54953  |
| GBPUSD   |             0           |         0           |     0           |                      -1 |                           0.5 |                                  0.5 |                      nan        |                                 0.594654 |                                 0.491428 |                                 0.391254 |                                 0.194756 |
| USDJPY   |             0           |         0           |     0           |                      -1 |                           0.5 |                                  0.5 |                      nan        |                                 1.15762  |                                 1.05588  |                                 0.95754  |                                 0.761891 |
| USDCHF   |             1.64743e-05 |         9.88457e-05 |     3.29486e-05 |                      -1 |                           0.5 |                                  0.5 |                        1.03157  |                                 0.784079 |                                 0.68417  |                                 0.585102 |                                 0.384669 |

#### Plots
![stage_08_robustness_lb95](../../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../../figures/oco_bible/stage_08_overfit_symbol_panel.png)

### Auto Snapshot - Stage 08

- generated_at: `2026-03-15 12:55:53 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |   5060 |       11 |           2.76225 |                      2.6265  |                11 |
| GBPUSD   |        0.9 |  12546 |       11 |           2.78491 |                      2.71472 |                11 |
| USDJPY   |        0.9 |  15806 |       11 |           3.74847 |                      3.67449 |                11 |
| USDCHF   |        0.9 |   8360 |       11 |           2.03548 |                      1.95735 |                11 |
| AUDUSD   |        0.9 |   8310 |       11 |           1.77838 |                      1.69662 |                11 |
| USDCAD   |        0.9 |   9254 |       10 |           2.49989 |                      2.41282 |                10 |

#### Interpretation Notes
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Details
| symbol   |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   t01_stress_elasticity |   t02_first_negative_costplus |   t04_max_survivable_cost_lb95_trade |   t03_post_worst_month_recovery |   lb95_trade_mean_net_pips_costplus_0.10 |   lb95_trade_mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.30 |   lb95_trade_mean_net_pips_costplus_0.50 |
|:---------|------------------------:|--------------------:|----------------:|------------------------:|------------------------------:|-------------------------------------:|--------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|
| EURUSD   |             1.24678e-13 |         7.48068e-13 |     2.49356e-13 |                      -1 |                           0.5 |                                  0.5 |                         1.23191 |                                  2.53532 |                                  2.43945 |                                  2.33035 |                                  2.13065 |
| GBPUSD   |             0           |         0           |     0           |                      -1 |                           0.5 |                                  0.5 |                         1.13248 |                                  2.6172  |                                  2.51581 |                                  2.42053 |                                  2.20749 |
| USDJPY   |             0           |         0           |     0           |                      -1 |                           0.5 |                                  0.5 |                         1.39396 |                                  3.57536 |                                  3.47177 |                                  3.37169 |                                  3.17399 |
| USDCHF   |             9.80327e-14 |         5.88196e-13 |     1.13354e-13 |                      -1 |                           0.5 |                                  0.5 |                         1.63825 |                                  1.85232 |                                  1.74718 |                                  1.63919 |                                  1.44377 |
| AUDUSD   |             1.49658e-13 |         8.97948e-13 |     2.99316e-13 |                      -1 |                           0.5 |                                  0.5 |                         3.53265 |                                  1.60424 |                                  1.49651 |                                  1.39921 |                                  1.18912 |
| USDCAD   |             1.11022e-16 |         6.66134e-16 |     6.66134e-16 |                      -1 |                           0.5 |                                  0.5 |                         2.77535 |                                  2.30955 |                                  2.20485 |                                  2.11024 |                                  1.91202 |

#### Plots
![stage_08_robustness_lb95](../../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../../figures/oco_bible/stage_08_overfit_symbol_panel.png)

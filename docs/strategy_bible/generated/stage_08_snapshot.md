### Auto Snapshot - Stage 08

- generated_at: `2026-02-26 22:19:06 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 | 325515 |        9 |           1.03932 |                      1.02232 |                 9 |
| GBPUSD   |        0.9 | 414128 |        9 |           1.01745 |                      1.00211 |                 9 |
| USDJPY   |        0.9 | 459585 |        9 |           1.37853 |                      1.36145 |                 9 |

#### Details
| symbol   |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   lb95_trade_mean_net_pips_costplus_0.00 |   lb95_trade_mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.40 |   lb95_trade_mean_net_pips_costplus_0.60 |
|:---------|------------------------:|--------------------:|----------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|
| EURUSD   |             1.15261e-09 |         1.15261e-09 |     1.15261e-09 |                                  1.02232 |                                 0.821562 |                                 0.621901 |                                 0.423091 |
| GBPUSD   |             0           |         0           |     0           |                                  1.00211 |                                 0.804603 |                                 0.603551 |                                 0.404395 |
| USDJPY   |             0           |         0           |     0           |                                  1.36145 |                                 1.16268  |                                 0.961219 |                                 0.762256 |

#### Plots
![stage_08_robustness_lb95](../../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../../figures/oco_bible/stage_08_overfit_symbol_panel.png)

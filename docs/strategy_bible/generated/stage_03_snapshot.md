### Auto Snapshot - Stage 03

- generated_at: `2026-03-11 21:50:05 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |       14 |   0.521779 |     0.249732 |       3.79276e+06 |                  4.30025  |           0.00132205  |                0.130227  |
| GBPUSD   |       14 |   0.523117 |     0.249639 |       4.59833e+06 |                  1.43409  |           0.000769545 |                0.0738935 |
| AUDUSD   |       14 |   0.522254 |     0.251136 |       4.18266e+06 |                  0.572776 |           0.000946094 |                0.162401  |
| USDJPY   |       14 |   0.526009 |     0.247588 |       4.81562e+06 |                  1.94653  |           0.000700228 |                0.0452724 |
| USDCHF   |       14 |   0.530064 |     0.250296 |       3.95814e+06 |                  1.48074  |           0.00159589  |                0.199366  |
| USDCAD   |       14 |   0.537569 |     0.249334 |       4.44682e+06 |                  1.97218  |           0.0037627   |                0.174985  |

#### Interpretation Notes
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Action Trigger Summary
| symbol   | metric_id               | band   | severity   | action_code           | action_summary         | owner    |
|:---------|:------------------------|:-------|:-----------|:----------------------|:-----------------------|:---------|
| AUDUSD   | W13_threshold_fragility | green  | info       | A0_MONITOR            | within policy band     | research |
| AUDUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| AUDUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |
| EURUSD   | W13_threshold_fragility | red    | high       | A3_HALT_AND_REMEDIATE | escalate and remediate | research |
| EURUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| EURUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |
| GBPUSD   | W13_threshold_fragility | green  | info       | A0_MONITOR            | within policy band     | research |
| GBPUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| GBPUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |
| USDCAD   | W13_threshold_fragility | amber  | medium     | A2_RECALIBRATE        | review and monitor     | research |
| USDCAD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| USDCAD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |

#### Details
| symbol   |   months |   mean_coverage |   mean_gross_pips |   rows_selected |
|:---------|---------:|----------------:|------------------:|----------------:|
| AUDUSD   |       14 |       0.0897709 |          0.449535 |          415660 |
| EURUSD   |       14 |       0.0962194 |          1.46115  |          431387 |
| GBPUSD   |       14 |       0.0897346 |          0.96337  |          425220 |
| USDCAD   |       14 |       0.0893935 |          0.824392 |          490796 |
| USDCHF   |       14 |       0.0843316 |          0.599204 |          348850 |
| USDJPY   |       14 |       0.0977184 |          1.37202  |          463768 |

#### Plots
![stage_03_wfo_monthly_gross](../../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          1.15137  |  0.191809  |         57851.1 |
| EURUSD   | aggregate    |       0.9  |          1.46115  |  0.0962194 |         30813.4 |
| EURUSD   | aggregate    |       0.95 |          1.79641  |  0.0474474 |         15976.1 |
| GBPUSD   | aggregate    |       0.8  |          0.848037 |  0.185145  |         61979.6 |
| GBPUSD   | aggregate    |       0.9  |          0.96337  |  0.0897346 |         30372.9 |
| GBPUSD   | aggregate    |       0.95 |          1.06315  |  0.0418456 |         14327.1 |
| AUDUSD   | aggregate    |       0.8  |          0.41137  |  0.192869  |         60849.6 |
| AUDUSD   | aggregate    |       0.9  |          0.449535 |  0.0897709 |         29690   |
| AUDUSD   | aggregate    |       0.95 |          0.497286 |  0.0394586 |         14047.1 |
| USDJPY   | aggregate    |       0.8  |          1.20166  |  0.196789  |         66914.2 |
| USDJPY   | aggregate    |       0.9  |          1.37202  |  0.0977184 |         33126.3 |
| USDJPY   | aggregate    |       0.95 |          1.49364  |  0.0485493 |         16319.5 |
| USDCHF   | aggregate    |       0.8  |          0.522041 |  0.177115  |         51441.7 |
| USDCHF   | aggregate    |       0.9  |          0.599204 |  0.0843316 |         24917.9 |
| USDCHF   | aggregate    |       0.95 |          0.744152 |  0.0387301 |         11500.4 |
| USDCAD   | aggregate    |       0.8  |          0.680782 |  0.187831  |         67802.1 |
| USDCAD   | aggregate    |       0.9  |          0.824392 |  0.0893935 |         35056.9 |
| USDCAD   | aggregate    |       0.95 |          0.976609 |  0.0412976 |         17635.4 |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   7789 |       11 |                11 |                      1.59632 |                          1.59632 |                                  1.18207 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   5934 |       10 |                10 |                      2.72549 |                          2.72549 |                                  1.82044 |             1.88738e-15 |         1.13243e-14 |     5.66214e-15 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |  12161 |       11 |                11 |                      2.69625 |                          2.69625 |                                  2.50797 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   7809 |       11 |                11 |                      2.21911 |                          2.21911 |                                  1.29081 |             8.88178e-16 |         5.32907e-15 |     5.32907e-15 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |  10408 |       11 |                11 |                      2.07321 |                          2.07321 |                                  1.28667 |             4.32987e-14 |         2.59792e-13 |     2.59792e-13 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |  13266 |       11 |                11 |                      3.79579 |                          3.79579 |                                  3.40256 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: these diagnostics are computed on WFO out-of-sample predictions only.
- `bonferroni_pass_10pct` and `fdr_pass_10pct` summarize multiplicity-adjusted significance at alpha=0.10.

#### Leakage/Label Integrity (WFO Focus)
| symbol   |   checks_total |   checks_failed |   high_critical_failed |
|:---------|---------------:|----------------:|-----------------------:|
| EURUSD   |              6 |               0 |                      0 |
| GBPUSD   |              6 |               0 |                      0 |
| AUDUSD   |              6 |               0 |                      0 |
| USDJPY   |              6 |               0 |                      0 |
| USDCHF   |              6 |               0 |                      0 |
| USDCAD   |              6 |               0 |                      0 |

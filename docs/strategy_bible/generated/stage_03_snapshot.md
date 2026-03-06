### Auto Snapshot - Stage 03

- generated_at: `2026-03-06 13:50:11 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |       14 |   0.521058 |     0.249811 |       3.87637e+06 |                   4.12988 |           0.00156103  |                0.115805  |
| GBPUSD   |       14 |   0.52274  |     0.249559 |       4.6661e+06  |                   1.3026  |           0.000638987 |                0.0662832 |
| AUDUSD   |       14 |   0.520134 |     0.251159 |       4.13824e+06 |                   1.01306 |           0.00077758  |                0.141851  |
| USDJPY   |       14 |   0.52614  |     0.247644 |       4.86343e+06 |                   1.92839 |           0.000864564 |                0.0425828 |
| USDCHF   |       14 |   0.520758 |     0.251276 |       4.05714e+06 |                   1.34019 |           0.00152487  |                0.177854  |
| USDCAD   |       14 |   0.523558 |     0.250769 |       4.53858e+06 |                   2.5201  |           0.00223613  |                0.139755  |

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
| AUDUSD   |       14 |       0.0879804 |          0.43899  |          413222 |
| EURUSD   |       14 |       0.102354  |          1.45236  |          454544 |
| GBPUSD   |       14 |       0.0907787 |          0.978087 |          432459 |
| USDCAD   |       14 |       0.092914  |          0.809392 |          527101 |
| USDCHF   |       14 |       0.0851227 |          0.599941 |          362854 |
| USDJPY   |       14 |       0.0968079 |          1.38414  |          460088 |

#### Plots
![stage_03_wfo_monthly_gross](../../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          1.11873  |  0.196903  |         60288.9 |
| EURUSD   | aggregate    |       0.9  |          1.45236  |  0.102354  |         32467.4 |
| EURUSD   | aggregate    |       0.95 |          1.73821  |  0.0527873 |         16903   |
| GBPUSD   | aggregate    |       0.8  |          0.851041 |  0.190134  |         64324.8 |
| GBPUSD   | aggregate    |       0.9  |          0.978087 |  0.0907787 |         30889.9 |
| GBPUSD   | aggregate    |       0.95 |          1.04643  |  0.041657  |         14265   |
| AUDUSD   | aggregate    |       0.8  |          0.367949 |  0.189533  |         59707.5 |
| AUDUSD   | aggregate    |       0.9  |          0.43899  |  0.0879804 |         29515.9 |
| AUDUSD   | aggregate    |       0.95 |          0.519908 |  0.0394143 |         14340.9 |
| USDJPY   | aggregate    |       0.8  |          1.21944  |  0.195744  |         66842.7 |
| USDJPY   | aggregate    |       0.9  |          1.38414  |  0.0968079 |         32863.4 |
| USDJPY   | aggregate    |       0.95 |          1.5087   |  0.0477232 |         16000.5 |
| USDCHF   | aggregate    |       0.8  |          0.502115 |  0.18352   |         54374.8 |
| USDCHF   | aggregate    |       0.9  |          0.599941 |  0.0851227 |         25918.1 |
| USDCHF   | aggregate    |       0.95 |          0.703143 |  0.0374829 |         11724.9 |
| USDCAD   | aggregate    |       0.8  |          0.640073 |  0.192649  |         71700.5 |
| USDCAD   | aggregate    |       0.9  |          0.809392 |  0.092914  |         37650.1 |
| USDCAD   | aggregate    |       0.95 |          1.01809  |  0.0428939 |         19015   |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   8335 |       11 |                11 |                      1.75361 |                          1.75361 |                                  1.07118 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   6197 |       11 |                11 |                      2.51145 |                          2.51145 |                                  1.66209 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |  12754 |       11 |                11 |                      2.5427  |                          2.5427  |                                  2.45726 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   8460 |       11 |                11 |                      2.07781 |                          2.07781 |                                  1.16625 |             5.36238e-13 |         3.21743e-12 |     3.21743e-12 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   9685 |       11 |                11 |                      1.99965 |                          1.99965 |                                  1.31101 |             1.77636e-14 |         1.06581e-13 |     3.55271e-14 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |  12137 |       11 |                11 |                      3.95632 |                          3.95632 |                                  3.6095  |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

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

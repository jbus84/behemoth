### Auto Snapshot - Stage 03

- generated_at: `2026-03-01 16:47:53 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |       14 |   0.520829 |     0.249754 |       3.84452e+06 |                  4.39352  |           0.00124197  |                0.121457  |
| GBPUSD   |        9 |   0.522514 |     0.24961  |       4.2722e+06  |                  1.25854  |           0.000778954 |                0.0593122 |
| AUDUSD   |        9 |   0.558639 |     0.24679  |       4.00769e+06 |                  0.780674 |           0.00193246  |                0.113443  |
| USDJPY   |        9 |   0.526568 |     0.247866 |       4.5452e+06  |                  1.50447  |           0.000967283 |                0.0163693 |
| USDCHF   |        9 |   0.543015 |     0.249483 |       3.74021e+06 |                  1.30968  |           0.00115577  |                0.166349  |
| USDCAD   |        9 |   0.554473 |     0.246616 |       3.43002e+06 |                  1.41019  |           0.00197814  |                0.129238  |

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
| USDCAD   | W13_threshold_fragility | green  | info       | A0_MONITOR            | within policy band     | research |
| USDCAD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| USDCAD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |

#### Details
| symbol   |   months |   mean_coverage |   mean_gross_pips |   rows_selected |
|:---------|---------:|----------------:|------------------:|----------------:|
| AUDUSD   |        9 |       0.0965678 |          0.453068 |          400871 |
| EURUSD   |       14 |       0.0958663 |          1.44296  |          395239 |
| GBPUSD   |        9 |       0.096381  |          0.996288 |          414128 |
| USDCAD   |        9 |       0.0955901 |          0.639585 |          348308 |
| USDCHF   |        9 |       0.097029  |          0.721884 |          366516 |
| USDJPY   |        9 |       0.101975  |          1.33948  |          459585 |

#### Plots
![stage_03_wfo_monthly_gross](../../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          1.10728  |  0.192056  |         55402.4 |
| EURUSD   | aggregate    |       0.9  |          1.44296  |  0.0958663 |         28231.4 |
| EURUSD   | aggregate    |       0.95 |          1.76631  |  0.0476827 |         14324   |
| GBPUSD   | aggregate    |       0.8  |          0.870914 |  0.196065  |         93435.1 |
| GBPUSD   | aggregate    |       0.9  |          0.996288 |  0.096381  |         46014.2 |
| GBPUSD   | aggregate    |       0.95 |          1.0597   |  0.0463834 |         22195.2 |
| AUDUSD   | aggregate    |       0.8  |          0.400825 |  0.196605  |         89270.2 |
| AUDUSD   | aggregate    |       0.9  |          0.453068 |  0.0965678 |         44541.2 |
| AUDUSD   | aggregate    |       0.95 |          0.517926 |  0.0467562 |         21882.4 |
| USDJPY   | aggregate    |       0.8  |          1.1889   |  0.202026  |        101383   |
| USDJPY   | aggregate    |       0.9  |          1.33948  |  0.101975  |         51065   |
| USDJPY   | aggregate    |       0.95 |          1.41457  |  0.0514609 |         25614.4 |
| USDCHF   | aggregate    |       0.8  |          0.613991 |  0.19583   |         81513.1 |
| USDCHF   | aggregate    |       0.9  |          0.721884 |  0.097029  |         40724   |
| USDCHF   | aggregate    |       0.95 |          0.810443 |  0.0471862 |         19976.1 |
| USDCAD   | aggregate    |       0.8  |          0.537391 |  0.196259  |         77823.9 |
| USDCAD   | aggregate    |       0.9  |          0.639585 |  0.0955901 |         38700.9 |
| USDCAD   | aggregate    |       0.95 |          0.74892  |  0.0448588 |         18380.8 |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   4188 |        6 |                 6 |                     0.879711 |                              nan |                                      nan |              0          |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   6982 |       11 |                11 |                     2.41589  |                              nan |                                      nan |              0          |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |   6890 |        6 |                 6 |                     2.57358  |                              nan |                                      nan |              0          |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   3874 |        6 |                 6 |                     1.1828   |                              nan |                                      nan |              7.9714e-14 |         4.78284e-13 |     2.39142e-13 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   4173 |        6 |                 6 |                     1.43592  |                              nan |                                      nan |              0          |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |   7940 |        6 |                 6 |                     3.42238  |                              nan |                                      nan |              0          |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: these diagnostics are computed on WFO out-of-sample predictions only.
- `bonferroni_pass_10pct` and `fdr_pass_10pct` summarize multiplicity-adjusted significance at alpha=0.10.

#### Leakage/Label Integrity (WFO Focus)
| symbol   |   checks_total |   checks_failed |   high_critical_failed |
|:---------|---------------:|----------------:|-----------------------:|
| EURUSD   |              6 |               0 |                      0 |
| GBPUSD   |              6 |               0 |                      0 |
| AUDUSD   |              6 |               0 |                      0 |
| USDJPY   |              6 |               0 |                      0 |
| USDCAD   |              6 |               1 |                      1 |

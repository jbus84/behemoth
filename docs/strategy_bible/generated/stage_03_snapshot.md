### Auto Snapshot - Stage 03

- generated_at: `2026-02-28 19:27:56 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |        9 |   0.526973 |     0.249766 |       3.3563e+06  |                  1.34602  |            0.00162703 |                0.0799501 |
| GBPUSD   |        9 |   0.51732  |     0.251184 |   46722           |                  0.700198 |            0.00128023 |                0.137968  |
| AUDUSD   |        9 |   0.558639 |     0.24679  |       4.00769e+06 |                  0.780674 |            0.00193246 |                0.113443  |
| USDJPY   |        9 |   0.52696  |     0.247879 |   51512           |                  0.5354   |            0.00217768 |                0.175758  |
| USDCHF   |        9 |   0.543015 |     0.249483 |       3.74021e+06 |                  1.30968  |            0.00115577 |                0.166349  |

#### Interpretation Notes
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Action Trigger Summary
| symbol   | metric_id               | band   | severity   | action_code   | action_summary     | owner    |
|:---------|:------------------------|:-------|:-----------|:--------------|:-------------------|:---------|
| EURUSD   | W13_threshold_fragility | green  | info       | A0_MONITOR    | within policy band | research |
| EURUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR    | within policy band | research |
| EURUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | W13_threshold_fragility | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | W13_threshold_fragility | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | W14_brier_drift_std     | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | W15_selection_turnover  | green  | info       | A0_MONITOR    | within policy band | research |

#### Details
| symbol   |   months |   mean_coverage |   mean_gross_pips |   rows_selected |
|:---------|---------:|----------------:|------------------:|----------------:|
| AUDUSD   |        9 |       0.0965678 |          0.453068 |          400871 |
| EURUSD   |        9 |       0.0953233 |          0.884677 |          325515 |
| GBPUSD   |        9 |       0.0945693 |          0.784329 |            4427 |
| USDCHF   |        9 |       0.097029  |          0.721884 |          366516 |
| USDJPY   |        9 |       0.0964553 |          1.39854  |            4939 |

#### Plots
![stage_03_wfo_monthly_gross](../../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          0.758561 |  0.191746  |       72544.3   |
| EURUSD   | aggregate    |       0.9  |          0.884677 |  0.0953233 |       36168.3   |
| EURUSD   | aggregate    |       0.95 |          0.960465 |  0.0475931 |       18029.7   |
| GBPUSD   | aggregate    |       0.8  |          0.795246 |  0.193268  |        1005.22  |
| GBPUSD   | aggregate    |       0.9  |          0.784329 |  0.0945693 |         491.889 |
| GBPUSD   | aggregate    |       0.95 |          0.690217 |  0.0459482 |         238.778 |
| AUDUSD   | aggregate    |       0.8  |          0.400825 |  0.196605  |       89270.2   |
| AUDUSD   | aggregate    |       0.9  |          0.453068 |  0.0965678 |       44541.2   |
| AUDUSD   | aggregate    |       0.95 |          0.517926 |  0.0467562 |       21882.4   |
| USDJPY   | aggregate    |       0.8  |          1.31823  |  0.196447  |        1120.89  |
| USDJPY   | aggregate    |       0.9  |          1.39854  |  0.0964553 |         548.778 |
| USDJPY   | aggregate    |       0.95 |          1.32811  |  0.0468008 |         264.444 |
| USDCHF   | aggregate    |       0.8  |          0.613991 |  0.19583   |       81513.1   |
| USDCHF   | aggregate    |       0.9  |          0.721884 |  0.097029  |       40724     |
| USDCHF   | aggregate    |       0.95 |          0.810443 |  0.0471862 |       19976.1   |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| EURUSD   |        0.9 |   4923 |        6 |                 6 |                     1.60064  |                              nan |                                      nan |             1.78644e-11 |         1.07186e-10 |     2.67966e-11 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |   4427 |        9 |                 9 |                     0.696371 |                              nan |                                      nan |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   4173 |        6 |                 6 |                     1.43592  |                              nan |                                      nan |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |   4939 |        9 |                 9 |                     1.25936  |                              nan |                                      nan |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: these diagnostics are computed on WFO out-of-sample predictions only.
- `bonferroni_pass_10pct` and `fdr_pass_10pct` summarize multiplicity-adjusted significance at alpha=0.10.

#### Leakage/Label Integrity (WFO Focus)
| symbol   |   checks_total |   checks_failed |   high_critical_failed |
|:---------|---------------:|----------------:|-----------------------:|
| EURUSD   |              6 |               0 |                      0 |
| GBPUSD   |              6 |               0 |                      0 |
| USDJPY   |              6 |               0 |                      0 |

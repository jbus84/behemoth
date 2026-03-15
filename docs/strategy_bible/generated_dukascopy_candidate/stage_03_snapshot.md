### Auto Snapshot - Stage 03

- generated_at: `2026-03-15 12:55:53 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |       14 |   0.521748 |     0.249809 |       3.9033e+06  |                   6.62459 |           0.00132817  |                0.118256  |
| GBPUSD   |       14 |   0.521334 |     0.249716 |       4.7354e+06  |                   1.58038 |           0.000820114 |                0.0542282 |
| USDJPY   |       14 |   0.528875 |     0.247113 |       4.81732e+06 |                   2.41027 |           0.000674206 |                0.0481423 |
| USDCHF   |       14 |   0.520121 |     0.251009 |       3.95252e+06 |                   1.37584 |           0.00105243  |                0.194267  |
| AUDUSD   |       14 |   0.525094 |     0.250711 |       4.24955e+06 |                   1.60278 |           0.000924204 |                0.148347  |
| USDCAD   |       14 |   0.523962 |     0.250672 |       4.53011e+06 |                   3.34186 |           0.00198902  |                0.141512  |

#### Interpretation Notes
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Details
| symbol   |   months |   mean_coverage |   mean_gross_pips |   rows_selected |
|:---------|---------:|----------------:|------------------:|----------------:|
| AUDUSD   |       14 |       0.0905768 |          0.578304 |          449651 |
| EURUSD   |       14 |       0.0949393 |          1.5992   |          422980 |
| GBPUSD   |       14 |       0.0906083 |          0.966919 |          437491 |
| USDCAD   |       14 |       0.0890661 |          0.939217 |          485352 |
| USDCHF   |       14 |       0.084881  |          0.561598 |          347520 |
| USDJPY   |       14 |       0.0983473 |          1.53159  |          475390 |

#### Plots
![stage_03_wfo_monthly_gross](../../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          1.17468  |  0.192331  |         58304.6 |
| EURUSD   | aggregate    |       0.9  |          1.5992   |  0.0949393 |         30212.9 |
| EURUSD   | aggregate    |       0.95 |          2.16836  |  0.0459309 |         15385.2 |
| GBPUSD   | aggregate    |       0.8  |          0.843159 |  0.189227  |         65063.6 |
| GBPUSD   | aggregate    |       0.9  |          0.966919 |  0.0906083 |         31249.4 |
| GBPUSD   | aggregate    |       0.95 |          1.08022  |  0.0415122 |         14382.6 |
| USDJPY   | aggregate    |       0.8  |          1.32546  |  0.199085  |         68340.7 |
| USDJPY   | aggregate    |       0.9  |          1.53159  |  0.0983473 |         33956.4 |
| USDJPY   | aggregate    |       0.95 |          1.687    |  0.0488615 |         16954.6 |
| USDCHF   | aggregate    |       0.8  |          0.496481 |  0.181902  |         52655.5 |
| USDCHF   | aggregate    |       0.9  |          0.561598 |  0.084881  |         24822.9 |
| USDCHF   | aggregate    |       0.95 |          0.702856 |  0.0381479 |         11387.6 |
| AUDUSD   | aggregate    |       0.8  |          0.496003 |  0.190222  |         62565.4 |
| AUDUSD   | aggregate    |       0.9  |          0.578304 |  0.0905768 |         32117.9 |
| AUDUSD   | aggregate    |       0.95 |          0.736421 |  0.0411968 |         16283.1 |
| USDCAD   | aggregate    |       0.8  |          0.738778 |  0.191605  |         69912.5 |
| USDCAD   | aggregate    |       0.9  |          0.939217 |  0.0890661 |         34668   |
| USDCAD   | aggregate    |       0.95 |          1.24006  |  0.0381265 |         15945.9 |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   8310 |       11 |                11 |                      1.69662 |                          1.69662 |                                  1.01894 |             1.49658e-13 |         8.97948e-13 |     2.99316e-13 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   5060 |       11 |                11 |                      2.6265  |                          2.6265  |                                  1.6823  |             1.24678e-13 |         7.48068e-13 |     2.49356e-13 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |  12546 |       11 |                11 |                      2.71472 |                          2.71472 |                                  2.56583 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   9254 |       10 |                10 |                      2.41282 |                          2.41282 |                                  1.381   |             1.11022e-16 |         6.66134e-16 |     6.66134e-16 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   8360 |       11 |                11 |                      1.95735 |                          1.95735 |                                  1.24529 |             9.80327e-14 |         5.88196e-13 |     1.13354e-13 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |  15806 |       11 |                11 |                      3.67449 |                          3.67449 |                                  3.41992 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: these diagnostics are computed on WFO out-of-sample predictions only.
- `bonferroni_pass_10pct` and `fdr_pass_10pct` summarize multiplicity-adjusted significance at alpha=0.10.

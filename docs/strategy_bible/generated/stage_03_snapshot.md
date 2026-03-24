### Auto Snapshot - Stage 03

- generated_at: `2026-03-23 20:05:07 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |       14 |   0.522117 |     0.249726 |       3.79276e+06 |                  4.48712  |           0.00120268  |                0.12881   |
| GBPUSD   |       14 |   0.522755 |     0.249691 |       4.59833e+06 |                  1.37426  |           0.000756223 |                0.0702232 |
| AUDUSD   |       14 |   0.521318 |     0.251285 |       4.18266e+06 |                  0.246836 |           0.00114929  |                0.161069  |
| USDJPY   |       14 |   0.525993 |     0.247629 |       4.81562e+06 |                  1.90751  |           0.000670593 |                0.0498448 |
| USDCHF   |       14 |   0.530781 |     0.250383 |       3.95814e+06 |                  1.20235  |           0.00158533  |                0.200269  |
| USDCAD   |       14 |   0.537559 |     0.249512 |       4.44682e+06 |                  1.8053   |           0.00434124  |                0.170166  |

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
| AUDUSD   |       14 |       0.0867933 |          0.444395 |          385590 |
| EURUSD   |       14 |       0.0979343 |          1.48716  |          441961 |
| GBPUSD   |       14 |       0.0908547 |          0.976386 |          431157 |
| USDCAD   |       14 |       0.0908904 |          0.795266 |          501026 |
| USDCHF   |       14 |       0.085702  |          0.605654 |          348977 |
| USDJPY   |       14 |       0.0990242 |          1.37201  |          471371 |

#### Plots
![stage_03_wfo_monthly_gross](../../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          1.16522  |  0.194405  |         58793.1 |
| EURUSD   | aggregate    |       0.9  |          1.48716  |  0.0979343 |         31568.6 |
| EURUSD   | aggregate    |       0.95 |          1.83829  |  0.0482059 |         16520.4 |
| GBPUSD   | aggregate    |       0.8  |          0.849294 |  0.187787  |         62926.1 |
| GBPUSD   | aggregate    |       0.9  |          0.976386 |  0.0908547 |         30796.9 |
| GBPUSD   | aggregate    |       0.95 |          1.05543  |  0.0424836 |         14606.9 |
| AUDUSD   | aggregate    |       0.8  |          0.407369 |  0.188395  |         58060.1 |
| AUDUSD   | aggregate    |       0.9  |          0.444395 |  0.0867933 |         27542.1 |
| AUDUSD   | aggregate    |       0.95 |          0.436704 |  0.0374703 |         12511.7 |
| USDJPY   | aggregate    |       0.8  |          1.19693  |  0.198657  |         67582.6 |
| USDJPY   | aggregate    |       0.9  |          1.37201  |  0.0990242 |         33669.4 |
| USDJPY   | aggregate    |       0.95 |          1.48306  |  0.0500855 |         16949.6 |
| USDCHF   | aggregate    |       0.8  |          0.520265 |  0.178122  |         51187.2 |
| USDCHF   | aggregate    |       0.9  |          0.605654 |  0.085702  |         24926.9 |
| USDCHF   | aggregate    |       0.95 |          0.700617 |  0.0393531 |         11469.7 |
| USDCAD   | aggregate    |       0.8  |          0.679304 |  0.18913   |         68609.8 |
| USDCAD   | aggregate    |       0.9  |          0.795266 |  0.0908904 |         35787.6 |
| USDCAD   | aggregate    |       0.95 |          0.950099 |  0.0422888 |         18126   |

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

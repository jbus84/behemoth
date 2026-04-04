### Auto Snapshot - Stage 03

- generated_at: `2026-04-03 12:49:19 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |       14 |   0.517089 |     0.25015  |       3.86359e+06 |                  2.04868  |           0.00154002  |                0.120709  |
| GBPUSD   |       14 |   0.521998 |     0.24967  |       4.74485e+06 |                  1.38606  |           0.000781571 |                0.0546183 |
| AUDUSD   |       14 |   0.522247 |     0.25102  |       4.18303e+06 |                  0.92714  |           0.000959127 |                0.153671  |
| USDJPY   |       14 |   0.528486 |     0.247175 |       4.83799e+06 |                  1.845    |           0.000696843 |                0.0409897 |
| USDCHF   |       14 |   0.518784 |     0.251138 |       3.93902e+06 |                  0.888519 |           0.00101697  |                0.198637  |
| USDCAD   |       14 |   0.524212 |     0.250676 |       4.4997e+06  |                  1.97927  |           0.00195333  |                0.144763  |

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
| AUDUSD   |       14 |       0.0961567 |          0.48142  |          414609 |
| EURUSD   |       14 |       0.0992196 |          1.04213  |          398829 |
| GBPUSD   |       14 |       0.0959814 |          0.986833 |          457689 |
| USDCAD   |       14 |       0.0956646 |          0.854857 |          451709 |
| USDCHF   |       14 |       0.0938636 |          0.547514 |          373453 |
| USDJPY   |       14 |       0.0990668 |          1.48768  |          479434 |

#### Plots
![stage_03_wfo_monthly_gross](../../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          0.886409 |  0.199001  |         56253.3 |
| EURUSD   | aggregate    |       0.9  |          1.04213  |  0.0992196 |         28487.8 |
| EURUSD   | aggregate    |       0.95 |          1.19371  |  0.0488432 |         14284.4 |
| GBPUSD   | aggregate    |       0.8  |          0.84776  |  0.194536  |         66228.7 |
| GBPUSD   | aggregate    |       0.9  |          0.986833 |  0.0959814 |         32692.1 |
| GBPUSD   | aggregate    |       0.95 |          1.05567  |  0.0468263 |         15967.1 |
| AUDUSD   | aggregate    |       0.8  |          0.419928 |  0.196799  |         59653.6 |
| AUDUSD   | aggregate    |       0.9  |          0.48142  |  0.0961567 |         29614.9 |
| AUDUSD   | aggregate    |       0.95 |          0.558999 |  0.0464994 |         14728.6 |
| USDJPY   | aggregate    |       0.8  |          1.30333  |  0.198473  |         68547.4 |
| USDJPY   | aggregate    |       0.9  |          1.48768  |  0.0990668 |         34245.3 |
| USDJPY   | aggregate    |       0.95 |          1.58008  |  0.0495882 |         17144.5 |
| USDCHF   | aggregate    |       0.8  |          0.493843 |  0.191748  |         54420.5 |
| USDCHF   | aggregate    |       0.9  |          0.547514 |  0.0938636 |         26675.2 |
| USDCHF   | aggregate    |       0.95 |          0.627121 |  0.0453808 |         12936.8 |
| USDCAD   | aggregate    |       0.8  |          0.686695 |  0.195617  |         65096.7 |
| USDCAD   | aggregate    |       0.9  |          0.854857 |  0.0956646 |         32264.9 |
| USDCAD   | aggregate    |       0.95 |          0.983585 |  0.0458307 |         15706.2 |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   8867 |       11 |                11 |                      1.56594 |                          1.56594 |                                  1.03458 |             4.41092e-12 |         2.64655e-11 |     5.2931e-12  |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   6771 |       11 |                11 |                      2.31991 |                          2.31991 |                                  1.6917  |             1.11022e-16 |         6.66134e-16 |     1.66533e-16 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |  13737 |       11 |                11 |                      2.63023 |                          2.63023 |                                  2.43777 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   6905 |       11 |                11 |                      1.66355 |                          1.66355 |                                  1.2799  |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   8287 |       11 |                11 |                      2.21857 |                          2.21857 |                                  1.19544 |             1.97176e-12 |         1.18305e-11 |     3.94351e-12 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |  17066 |       11 |                11 |                      3.58099 |                          3.58099 |                                  3.32542 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

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

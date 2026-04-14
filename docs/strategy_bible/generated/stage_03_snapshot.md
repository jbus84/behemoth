### Auto Snapshot - Stage 03

- generated_at: `2026-04-12 17:21:09 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |       15 |   0.562945 |     0.246676 |       1.1809e+06  |                  11.1458  |            0.0012583  |                0.148595  |
| GBPUSD   |       15 |   0.559669 |     0.247354 |       1.57376e+06 |                  11.5488  |            0.00345023 |                0.0888127 |
| AUDUSD   |       15 |   0.553093 |     0.252994 |  338823           |                   4.36777 |            0.00848581 |                0.149692  |
| USDJPY   |       15 |   0.566838 |     0.243187 |       2.69553e+06 |                  14.2697  |            0.00306899 |                0.102557  |
| USDCHF   |       15 |   0.560668 |     0.251174 |  315930           |                   3.26347 |            0.00936718 |                0.0935331 |
| USDCAD   |       15 |   0.575453 |     0.248875 |  514658           |                   6.0671  |            0.00486643 |                0.182531  |

#### Interpretation Notes
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Action Trigger Summary
| symbol   | metric_id               | band   | severity   | action_code           | action_summary         | owner    |
|:---------|:------------------------|:-------|:-----------|:----------------------|:-----------------------|:---------|
| AUDUSD   | W13_threshold_fragility | red    | high       | A3_HALT_AND_REMEDIATE | escalate and remediate | research |
| AUDUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| AUDUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |
| EURUSD   | W13_threshold_fragility | red    | high       | A3_HALT_AND_REMEDIATE | escalate and remediate | research |
| EURUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| EURUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |
| GBPUSD   | W13_threshold_fragility | red    | high       | A3_HALT_AND_REMEDIATE | escalate and remediate | research |
| GBPUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| GBPUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |
| USDCAD   | W13_threshold_fragility | red    | high       | A3_HALT_AND_REMEDIATE | escalate and remediate | research |
| USDCAD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| USDCAD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |

#### Details
| symbol   |   months |   mean_coverage |   mean_gross_pips |   rows_selected |
|:---------|---------:|----------------:|------------------:|----------------:|
| AUDUSD   |       15 |       0.0936419 |           3.51258 |           31197 |
| EURUSD   |       15 |       0.0919786 |           4.98662 |          114517 |
| GBPUSD   |       15 |       0.0868072 |           5.52202 |          138492 |
| USDCAD   |       15 |       0.0904706 |           3.9102  |           47190 |
| USDCHF   |       15 |       0.0914598 |           3.72152 |           28898 |
| USDJPY   |       15 |       0.0922324 |           7.67731 |          248355 |

#### Plots
![stage_03_wfo_monthly_gross](../../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |           3.95462 |  0.193036  |        15713.9  |
| EURUSD   | aggregate    |       0.9  |           4.98662 |  0.0919786 |         7634.47 |
| EURUSD   | aggregate    |       0.95 |           5.62649 |  0.0434    |         3673.6  |
| GBPUSD   | aggregate    |       0.8  |           4.50098 |  0.183932  |        19473.3  |
| GBPUSD   | aggregate    |       0.9  |           5.52202 |  0.0868072 |         9232.8  |
| GBPUSD   | aggregate    |       0.95 |           6.23331 |  0.0405422 |         4329.2  |
| AUDUSD   | aggregate    |       0.8  |           3.14617 |  0.194802  |         4296.87 |
| AUDUSD   | aggregate    |       0.9  |           3.51258 |  0.0936419 |         2079.8  |
| AUDUSD   | aggregate    |       0.95 |           3.80133 |  0.0450425 |         1008.87 |
| USDJPY   | aggregate    |       0.8  |           6.37546 |  0.191721  |        34426.4  |
| USDJPY   | aggregate    |       0.9  |           7.67731 |  0.0922324 |        16557    |
| USDJPY   | aggregate    |       0.95 |           8.51592 |  0.0436684 |         7832.6  |
| USDCHF   | aggregate    |       0.8  |           3.33974 |  0.189083  |         3977.93 |
| USDCHF   | aggregate    |       0.9  |           3.72152 |  0.0914598 |         1926.53 |
| USDCHF   | aggregate    |       0.95 |           3.82926 |  0.0434375 |          918.2  |
| USDCAD   | aggregate    |       0.8  |           3.37486 |  0.190804  |         6605.33 |
| USDCAD   | aggregate    |       0.9  |           3.9102  |  0.0904706 |         3146    |
| USDCAD   | aggregate    |       0.95 |           4.28493 |  0.0423984 |         1474.67 |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   2388 |        7 |                 7 |                      5.12738 |                          5.12738 |                                  5.22063 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   6430 |       12 |                12 |                      7.44487 |                          7.44487 |                                  6.77829 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |   7191 |       12 |                12 |                      7.50235 |                          7.50235 |                                  7.10403 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   4062 |       10 |                10 |                      5.28134 |                          5.28134 |                                  4.87833 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   1773 |        6 |                 6 |                      5.48371 |                          5.48371 |                                  4.74044 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |   5205 |       12 |                12 |                     10.7085  |                         10.7085  |                                 10.4879  |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: these diagnostics are computed on WFO out-of-sample predictions only.
- `bonferroni_pass_10pct` and `fdr_pass_10pct` summarize multiplicity-adjusted significance at alpha=0.10.

### Auto Snapshot - Stage 03

- generated_at: `2026-03-30 10:10:58 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |       14 |   0.522117 |     0.249726 |       3.79276e+06 |                  4.5967   |           0.00120268  |                0.127394  |
| GBPUSD   |       14 |   0.522755 |     0.249691 |       4.59833e+06 |                  1.32682  |           0.000756223 |                0.0702232 |
| AUDUSD   |       14 |   0.521318 |     0.251285 |       4.18266e+06 |                  0.302955 |           0.00114929  |                0.158005  |
| USDJPY   |       14 |   0.525993 |     0.247629 |       4.81562e+06 |                  1.91625  |           0.000670593 |                0.0467014 |
| USDCHF   |       14 |   0.530781 |     0.250383 |       3.95814e+06 |                  1.0948   |           0.00158533  |                0.201684  |
| USDCAD   |       14 |   0.537559 |     0.249512 |       4.44682e+06 |                  1.60515  |           0.00434124  |                0.167602  |

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
| AUDUSD   |       14 |       0.0963463 |          0.450128 |          406594 |
| EURUSD   |       14 |       0.0979161 |          1.47038  |          393419 |
| GBPUSD   |       14 |       0.0950574 |          0.971319 |          441619 |
| USDCAD   |       14 |       0.095205  |          0.831736 |          452740 |
| USDCHF   |       14 |       0.0922698 |          0.58784  |          366177 |
| USDJPY   |       14 |       0.0989874 |          1.36841  |          474576 |

#### Plots
![stage_03_wfo_monthly_gross](../../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          1.15288  |  0.196097  |         55184.4 |
| EURUSD   | aggregate    |       0.9  |          1.47038  |  0.0979161 |         28101.4 |
| EURUSD   | aggregate    |       0.95 |          1.84239  |  0.0482617 |         14102.5 |
| GBPUSD   | aggregate    |       0.8  |          0.839568 |  0.193759  |         64087.8 |
| GBPUSD   | aggregate    |       0.9  |          0.971319 |  0.0950574 |         31544.2 |
| GBPUSD   | aggregate    |       0.95 |          1.03859  |  0.0462123 |         15379.4 |
| AUDUSD   | aggregate    |       0.8  |          0.404684 |  0.197485  |         59362   |
| AUDUSD   | aggregate    |       0.9  |          0.450128 |  0.0963463 |         29042.4 |
| AUDUSD   | aggregate    |       0.95 |          0.434541 |  0.046134  |         14058.4 |
| USDJPY   | aggregate    |       0.8  |          1.19258  |  0.198798  |         68162.1 |
| USDJPY   | aggregate    |       0.9  |          1.36841  |  0.0989874 |         33898.3 |
| USDJPY   | aggregate    |       0.95 |          1.48002  |  0.0493764 |         16863.6 |
| USDCHF   | aggregate    |       0.8  |          0.510991 |  0.189967  |         53787.5 |
| USDCHF   | aggregate    |       0.9  |          0.58784  |  0.0922698 |         26155.5 |
| USDCHF   | aggregate    |       0.95 |          0.675212 |  0.044248  |         12529.8 |
| USDCAD   | aggregate    |       0.8  |          0.703142 |  0.194599  |         64663.1 |
| USDCAD   | aggregate    |       0.9  |          0.831736 |  0.095205  |         32338.6 |
| USDCAD   | aggregate    |       0.95 |          0.943914 |  0.0457489 |         15806.4 |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   6102 |       10 |                10 |                      1.51152 |                          1.51152 |                                  1.10136 |             6.95666e-13 |         4.17399e-12 |     1.39133e-12 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   4267 |       10 |                10 |                      2.42312 |                          2.42312 |                                  1.76235 |             1.62204e-13 |         9.73222e-13 |     2.30749e-13 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |   9776 |       11 |                11 |                      2.58253 |                          2.58253 |                                  2.45838 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   7942 |       11 |                11 |                      1.95503 |                          1.95503 |                                  1.16154 |             1.02516e-11 |         6.15095e-11 |     1.23019e-11 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   6782 |       11 |                11 |                      1.748   |                          1.748   |                                  1.26737 |             2.03171e-14 |         1.21902e-13 |     6.09512e-14 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |  10002 |       11 |                11 |                      3.79905 |                          3.79905 |                                  3.45121 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

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

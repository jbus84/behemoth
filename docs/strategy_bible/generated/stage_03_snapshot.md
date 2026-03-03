### Auto Snapshot - Stage 03

- generated_at: `2026-03-03 12:43:04 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |       14 |   0.520829 |     0.249754 |       3.84452e+06 |                  4.35448  |           0.00124197  |                0.12283   |
| GBPUSD   |        9 |   0.522514 |     0.24961  |       4.2722e+06  |                  1.30032  |           0.000778954 |                0.0593122 |
| AUDUSD   |        9 |   0.558639 |     0.24679  |       4.00769e+06 |                  0.602263 |           0.00193246  |                0.118638  |
| USDJPY   |        9 |   0.526568 |     0.247866 |       4.5452e+06  |                  1.40588  |           0.000967283 |                0.0180458 |
| USDCHF   |        9 |   0.543015 |     0.249483 |       3.74021e+06 |                  1.48632  |           0.00115577  |                0.168319  |
| USDCAD   |        9 |   0.554473 |     0.246616 |       3.43002e+06 |                  1.40148  |           0.00197814  |                0.130087  |

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
| AUDUSD   |        9 |       0.0948007 |          0.438534 |          444263 |
| EURUSD   |       14 |       0.0938823 |          1.44453  |          430032 |
| GBPUSD   |        9 |       0.0901245 |          1.00247  |          392129 |
| USDCAD   |        9 |       0.0864007 |          0.640127 |          379629 |
| USDCHF   |        9 |       0.0947093 |          0.714    |          370769 |
| USDJPY   |        9 |       0.103486  |          1.3468   |          459073 |

#### Plots
![stage_03_wfo_monthly_gross](../../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          1.12626  |  0.187925  |         58264.8 |
| EURUSD   | aggregate    |       0.9  |          1.44453  |  0.0938823 |         30716.6 |
| EURUSD   | aggregate    |       0.95 |          1.77943  |  0.0464319 |         15873.8 |
| GBPUSD   | aggregate    |       0.8  |          0.882124 |  0.188964  |         90758.9 |
| GBPUSD   | aggregate    |       0.9  |          1.00247  |  0.0901245 |         43569.9 |
| GBPUSD   | aggregate    |       0.95 |          1.07717  |  0.0404828 |         19733.4 |
| AUDUSD   | aggregate    |       0.8  |          0.393007 |  0.195918  |         94735.9 |
| AUDUSD   | aggregate    |       0.9  |          0.438534 |  0.0948007 |         49362.6 |
| AUDUSD   | aggregate    |       0.95 |          0.483347 |  0.0450423 |         25309.1 |
| USDJPY   | aggregate    |       0.8  |          1.19335  |  0.203998  |        100839   |
| USDJPY   | aggregate    |       0.9  |          1.3468   |  0.103486  |         51008.1 |
| USDJPY   | aggregate    |       0.95 |          1.40423  |  0.0530503 |         25854.7 |
| USDCHF   | aggregate    |       0.8  |          0.607276 |  0.190546  |         80748.3 |
| USDCHF   | aggregate    |       0.9  |          0.714    |  0.0947093 |         41196.6 |
| USDCHF   | aggregate    |       0.95 |          0.830224 |  0.0440711 |         19843.6 |
| USDCAD   | aggregate    |       0.8  |          0.541331 |  0.183475  |         80341.4 |
| USDCAD   | aggregate    |       0.9  |          0.640127 |  0.0864007 |         42181   |
| USDCAD   | aggregate    |       0.95 |          0.751553 |  0.038836  |         21503.2 |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   4227 |        6 |                 6 |                     0.952247 |                              nan |                                      nan |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   6715 |       11 |                11 |                     2.5027   |                              nan |                                      nan |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |   6978 |        6 |                 6 |                     2.57413  |                              nan |                                      nan |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   3574 |        6 |                 6 |                     1.41111  |                              nan |                                      nan |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   4170 |        6 |                 6 |                     1.37476  |                              nan |                                      nan |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |   8186 |        6 |                 6 |                     3.41566  |                              nan |                                      nan |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

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

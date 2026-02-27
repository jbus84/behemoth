### Auto Snapshot - Stage 03

- generated_at: `2026-02-27 18:50:29 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |        9 |   0.519102 |     0.249688 |            601419 |                   1.30001 |           0.00230192  |                0.0787872 |
| GBPUSD   |        9 |   0.521541 |     0.249106 |            724301 |                   1.15259 |           0.000844451 |                0.108208  |
| USDJPY   |        9 |   0.525886 |     0.24695  |            780202 |                   1.31649 |           0.000970862 |                0.0708162 |

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
| EURUSD   |        9 |       0.0963987 |          0.940788 |           59955 |
| GBPUSD   |        9 |       0.0975836 |          1.012    |           70579 |
| USDJPY   |        9 |       0.100711  |          1.36216  |           77785 |

#### Plots
![stage_03_wfo_monthly_gross](../../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          0.816448 |  0.195694  |        13411.9  |
| EURUSD   | aggregate    |       0.9  |          0.940788 |  0.0963987 |         6661.67 |
| EURUSD   | aggregate    |       0.95 |          1.01145  |  0.0476338 |         3299.33 |
| GBPUSD   | aggregate    |       0.8  |          0.912357 |  0.197712  |        15928.1  |
| GBPUSD   | aggregate    |       0.9  |          1.012    |  0.0975836 |         7842.11 |
| GBPUSD   | aggregate    |       0.95 |          1.08525  |  0.0476474 |         3816.22 |
| USDJPY   | aggregate    |       0.8  |          1.23456  |  0.200414  |        17284    |
| USDJPY   | aggregate    |       0.9  |          1.36216  |  0.100711  |         8642.78 |
| USDJPY   | aggregate    |       0.95 |          1.43203  |  0.0508893 |         4344.11 |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| EURUSD   |        0.9 |  59955 |        9 |                 9 |                     1.04912  |                              nan |                                      nan |              2.4283e-09 |         1.45698e-08 |     2.91396e-09 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |  70579 |        9 |                 9 |                     0.973913 |                              nan |                                      nan |              0          |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |  77785 |        9 |                 9 |                     1.33687  |                              nan |                                      nan |              0          |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: these diagnostics are computed on WFO out-of-sample predictions only.
- `bonferroni_pass_10pct` and `fdr_pass_10pct` summarize multiplicity-adjusted significance at alpha=0.10.

#### Leakage/Label Integrity (WFO Focus)
| symbol   |   checks_total |   checks_failed |   high_critical_failed |
|:---------|---------------:|----------------:|-----------------------:|
| EURUSD   |              6 |               0 |                      0 |
| GBPUSD   |              6 |               0 |                      0 |
| USDJPY   |              6 |               0 |                      0 |

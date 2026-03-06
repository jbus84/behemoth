### Auto Snapshot - Stage 02

- generated_at: `2026-03-05 20:17:32 UTC`
- selection_pass candidates are broad hypotheses only.
- Scatter shows the high-count >0 gross opportunity frontier.
- M01-M03 quantify concentration risk, horizon smoothness, and positive-edge density.

#### Key Results
| symbol   |   candidates_total |   selected_total |   selected_mean_gross_pips |   selected_median_annualized |   m01_top3_contrib_share |   m02_smoothness_abs_jump |   m03_positive_density |
|:---------|-------------------:|-----------------:|---------------------------:|-----------------------------:|-------------------------:|--------------------------:|-----------------------:|
| EURUSD   |               2160 |             1800 |                   2.73323  |                      4641.46 |                0.0326985 |                 0.247311  |               0.882222 |
| GBPUSD   |               2160 |             1685 |                   3.32768  |                      4814.26 |                0.0337978 |                 0.288919  |               0.910386 |
| AUDUSD   |               2160 |             1672 |                   2.1009   |                      2459.85 |                0.032903  |                 0.20972   |               0.910885 |
| USDJPY   |               2160 |             1742 |                   4.35846  |                      8170.66 |                0.0307445 |                 0.339244  |               0.889208 |
| USDCHF   |               2160 |             1489 |                   2.58074  |                      2808.79 |                0.0354318 |                 0.24956   |               0.8818   |
| USDCAD   |                720 |              669 |                   0.404258 |                      9234.52 |                0.0896167 |                 0.0592627 |               0.898356 |

#### Interpretation Notes
- selection_pass candidates are broad hypotheses only.
- Scatter shows the high-count >0 gross opportunity frontier.
- M01-M03 quantify concentration risk, horizon smoothness, and positive-edge density.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Plots
![stage_02_selected_scatter](../../figures/oco_bible/stage_02_selected_scatter.png)

#### Edge Contribution by State Block
| symbol   | family                | state_id                                    |   bar_ticks |   horizon |   edge_weight |   contrib_share |
|:---------|:----------------------|:--------------------------------------------|------------:|----------:|--------------:|----------------:|
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      122379   |      0.0127718  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |       97464.1 |      0.0101715  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |       95434.4 |      0.00995972 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |       74287.3 |      0.00775278 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |       74125.1 |      0.00773585 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |       67908   |      0.00708701 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         5 |       55668.8 |      0.00580971 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         6 |       55122.6 |      0.00575271 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      273060   |      0.0132643  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      225779   |      0.0109676  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      174293   |      0.00846657 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |      155374   |      0.00754755 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         6 |      145548   |      0.00707023 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      143860   |      0.00698821 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         5 |      124395   |      0.00604271 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         5 |      121071   |      0.00588121 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      316345   |      0.0125907  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      266813   |      0.0106193  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      266020   |      0.0105877  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |      224246   |      0.00892514 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      209899   |      0.0083541  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |      191214   |      0.00761041 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      180164   |      0.00717062 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         4 |      175963   |      0.00700343 |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      214555   |      0.0364454  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      176951   |      0.0300578  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      136070   |      0.0231136  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      108809   |      0.0184828  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__london__k2           |         100 |         6 |       96180.9 |      0.0163377  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         3 |       93635.8 |      0.0159054  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         5 |       83451.2 |      0.0141754  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         6 |       80799.5 |      0.013725   |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      159348   |      0.0145451  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      128335   |      0.0117142  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      100489   |      0.00917252 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |       96283.3 |      0.00878859 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |       78759.7 |      0.00718906 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |       73784.2 |      0.0067349  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |       73666.3 |      0.00672415 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2 |         100 |         6 |       65565.3 |      0.0059847  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      605018   |      0.0117861  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      531927   |      0.0103623  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      441263   |      0.00859607 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      426780   |      0.00831393 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      385493   |      0.00750965 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         5 |      338588   |      0.0065959  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |      336760   |      0.00656029 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         3 |      330929   |      0.00644671 |

#### Overfitting Diagnostics (Downstream, Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   4227 |        6 |                 6 |                     0.952247 |                         0.952247 |                                 0.839258 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   6715 |       11 |                11 |                     2.5027   |                         2.5027   |                                 1.80464  |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |   6978 |        6 |                 6 |                     2.57413  |                         2.57413  |                                 2.44927  |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   3574 |        6 |                 6 |                     1.41111  |                         1.41111  |                                 1.2101   |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   4170 |        6 |                 6 |                     1.37476  |                         1.37476  |                                 1.21468  |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |   8186 |        6 |                 6 |                     3.41566  |                         3.41566  |                                 3.15864  |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: Stage 2 mining is accepted only as hypothesis generation; false-discovery control is enforced downstream via Stage 3/8 out-of-sample evaluation.
- Multiplicity fields (`pvalue_bonferroni`, `pvalue_fdr_bh`) are reported at the execution quantile and should be used with LB95/month-consistency, not in isolation.

### Auto Snapshot - Stage 02

- generated_at: `2026-03-15 12:55:53 UTC`
- selection_pass candidates are broad hypotheses only.
- Scatter shows the high-count >0 gross opportunity frontier.
- M01-M03 quantify concentration risk, horizon smoothness, and positive-edge density.

#### Key Results
| symbol   |   candidates_total |   selected_total |   selected_mean_gross_pips |   selected_median_annualized |   m01_top3_contrib_share |   m02_smoothness_abs_jump |   m03_positive_density |
|:---------|-------------------:|-----------------:|---------------------------:|-----------------------------:|-------------------------:|--------------------------:|-----------------------:|
| EURUSD   |               2160 |             1697 |                    2.90498 |                      5029.01 |                0.0307137 |                  0.297391 |               0.895109 |
| GBPUSD   |               2160 |             1658 |                    3.34912 |                      4784.51 |                0.0340912 |                  0.285784 |               0.910133 |
| USDJPY   |               2160 |             1738 |                    4.43222 |                      8001.32 |                0.030283  |                  0.334308 |               0.955121 |
| USDCHF   |               2160 |             1450 |                    2.65273 |                      2801.84 |                0.0357437 |                  0.23732  |               0.910345 |
| AUDUSD   |               2160 |             1546 |                    2.26789 |                      2457.67 |                0.0327183 |                  0.200185 |               0.963777 |
| USDCAD   |               2160 |             1483 |                    2.68522 |                      2796.83 |                0.0418865 |                  0.236291 |               0.91706  |

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
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      122356   |      0.0126875  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |       97752.1 |      0.0101363  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |       95421.5 |      0.00989459 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |       76081.6 |      0.00788916 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |       74510.5 |      0.00772625 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |       67922.6 |      0.00704312 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         5 |       57137.8 |      0.00592482 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         6 |       54694.9 |      0.00567151 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      272797   |      0.0124427  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      226223   |      0.0103184  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      174357   |      0.00795266 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |      168618   |      0.0076909  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         6 |      154950   |      0.0070675  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      143897   |      0.00656335 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         5 |      132439   |      0.00604075 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         5 |      131306   |      0.00598908 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      315133   |      0.0126901  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      266499   |      0.0107317  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      264953   |      0.0106694  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |      224032   |      0.00902157 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      210536   |      0.00847808 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |      194478   |      0.00783142 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      180718   |      0.00727733 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         4 |      176415   |      0.00710408 |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      214977   |      0.016979   |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      178325   |      0.0140842  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      137039   |      0.0108234  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      110391   |      0.00871875 |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         3 |       94819.4 |      0.00748888 |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         5 |       85318.9 |      0.00673853 |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2       |         100 |         6 |       82404.5 |      0.00650834 |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         6 |       80517.5 |      0.00635931 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      159476   |      0.014637   |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      128262   |      0.0117721  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      101705   |      0.00933465 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |       95817   |      0.00879422 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |       79128.4 |      0.00726252 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |       75140.3 |      0.00689649 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |       73379.4 |      0.00673487 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2 |         100 |         6 |       66185.7 |      0.00607462 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      604820   |      0.0116106  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      531447   |      0.0102021  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      441228   |      0.0084702  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      426284   |      0.00818332 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      379440   |      0.00728405 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         5 |      338562   |      0.00649932 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |      331756   |      0.00636868 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         3 |      331752   |      0.00636861 |

#### Overfitting Diagnostics (Downstream, Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   8310 |       11 |                11 |                      1.69662 |                          1.69662 |                                  1.01894 |             1.49658e-13 |         8.97948e-13 |     2.99316e-13 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   5060 |       11 |                11 |                      2.6265  |                          2.6265  |                                  1.6823  |             1.24678e-13 |         7.48068e-13 |     2.49356e-13 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |  12546 |       11 |                11 |                      2.71472 |                          2.71472 |                                  2.56583 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   9254 |       10 |                10 |                      2.41282 |                          2.41282 |                                  1.381   |             1.11022e-16 |         6.66134e-16 |     6.66134e-16 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   8360 |       11 |                11 |                      1.95735 |                          1.95735 |                                  1.24529 |             9.80327e-14 |         5.88196e-13 |     1.13354e-13 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |  15806 |       11 |                11 |                      3.67449 |                          3.67449 |                                  3.41992 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: Stage 2 mining is accepted only as hypothesis generation; false-discovery control is enforced downstream via Stage 3/8 out-of-sample evaluation.
- Multiplicity fields (`pvalue_bonferroni`, `pvalue_fdr_bh`) are reported at the execution quantile and should be used with LB95/month-consistency, not in isolation.

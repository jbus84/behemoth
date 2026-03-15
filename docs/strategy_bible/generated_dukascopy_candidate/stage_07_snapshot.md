### Auto Snapshot - Stage 07

- generated_at: `2026-03-15 12:55:53 UTC`
- C01..C10 checks are the logical contract gate before robustness sign-off.
- Open issue rows: 0.

#### Key Results
| symbol   |   total_checks |   failed_checks |
|:---------|---------------:|----------------:|
| AUDUSD   |             10 |               0 |
| EURUSD   |             10 |               0 |
| GBPUSD   |             10 |               0 |
| USDCAD   |             10 |               0 |
| USDCHF   |             10 |               0 |
| USDJPY   |             10 |               0 |

#### Interpretation Notes
- C01..C10 checks are the logical contract gate before robustness sign-off.
- Open issue rows: 0.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Details
| check_id   | status   |   size |
|:-----------|:---------|-------:|
| C01        | pass     |      6 |
| C02        | pass     |      6 |
| C03        | pass     |      6 |
| C04        | pass     |      6 |
| C05        | pass     |      6 |
| C06        | pass     |      6 |
| C07        | pass     |      6 |
| C08        | pass     |      6 |
| C09        | pass     |      6 |
| C10        | pass     |      6 |

#### Plots
![stage_07_audit_failures](../../figures/oco_bible/stage_07_audit_failures.png)

#### Statistical Inference Ladder (S01-S03)
| symbol   |   lb95_trade_mean_gross_pips |   s01_lb95_dependence_gap |   pvalue_bonferroni |   pvalue_fdr_bh |   s02_practical_lb95_gt0 |   s03_multiplicity_survival |
|:---------|-----------------------------:|--------------------------:|--------------------:|----------------:|-------------------------:|----------------------------:|
| AUDUSD   |                      1.69662 |                  0.677684 |         8.97948e-13 |     2.99316e-13 |                        1 |                           1 |
| EURUSD   |                      2.6265  |                  0.944201 |         7.48068e-13 |     2.49356e-13 |                        1 |                           1 |
| GBPUSD   |                      2.71472 |                  0.148886 |         0           |     0           |                        1 |                           1 |
| USDCAD   |                      2.41282 |                  1.03181  |         6.66134e-16 |     6.66134e-16 |                        1 |                           1 |
| USDCHF   |                      1.95735 |                  0.712063 |         5.88196e-13 |     1.13354e-13 |                        1 |                           1 |
| USDJPY   |                      3.67449 |                  0.25457  |         0           |     0           |                        1 |                           1 |

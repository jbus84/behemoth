### Auto Snapshot - Stage 06

- generated_at: `2026-03-05 07:55:58 UTC`
- Verifier recomputes OCO outcomes independently from stored labels.
- All summary rates should remain near 1.0 for contract consistency.

#### Key Results
| symbol   |   rows_selected |   rows_verified |   exact_match_rate |   pos_label_match_rate | overall_pass   |
|:---------|----------------:|----------------:|-------------------:|-----------------------:|:---------------|
| EURUSD   |           28655 |           28655 |           1        |               1        | True           |
| GBPUSD   |           33524 |           33524 |           1        |               1        | True           |
| AUDUSD   |           29804 |           29804 |           0.976043 |               0.995403 | False          |
| USDJPY   |           30552 |           30552 |           1        |               1        | True           |
| USDCHF   |           30450 |           30450 |           0.985517 |               0.997209 | False          |
| USDCAD   |           34234 |           34234 |           1        |               1        | True           |

#### Interpretation Notes
- Verifier recomputes OCO outcomes independently from stored labels.
- All summary rates should remain near 1.0 for contract consistency.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Details
| symbol   |   months |   exact_min |   exact_mean |   pos_min |   pos_mean |
|:---------|---------:|------------:|-------------:|----------:|-----------:|
| AUDUSD   |        9 |    0.955958 |     0.988379 |  0.992012 |   0.997488 |
| EURUSD   |       14 |    1        |     1        |  1        |   1        |
| GBPUSD   |        9 |    1        |     1        |  1        |   1        |
| USDCAD   |        9 |    1        |     1        |  1        |   1        |
| USDCHF   |        9 |    0.978034 |     0.988734 |  0.995215 |   0.998223 |
| USDJPY   |        9 |    1        |     1        |  1        |   1        |

#### Plots
![stage_06_tick_exact_monthly](../../figures/oco_bible/stage_06_tick_exact_monthly.png)

#### Cross-Symbol Portability (X01-X03)
| family                |   symbols_covered |   mean_across_symbols |   std_across_symbols |   spread_max_min |   x01_all_symbols_positive |
|:----------------------|------------------:|----------------------:|---------------------:|-----------------:|---------------------------:|
| oco_first_touch_clean |                 6 |              4.00645  |            2.1113    |         6.32425  |                        nan |
| oco_first_touch       |                 6 |              0.166495 |            0.0481769 |         0.129843 |                        nan |

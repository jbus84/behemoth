### Auto Snapshot - Stage 06

- generated_at: `2026-03-30 10:10:58 UTC`
- Verifier recomputes OCO outcomes independently from stored labels.
- All summary rates should remain near 1.0 for contract consistency.

#### Key Results
| symbol   |   rows_selected |   rows_verified |   exact_match_rate |   pos_label_match_rate | overall_pass   |
|:---------|----------------:|----------------:|-------------------:|-----------------------:|:---------------|
| EURUSD   |            4659 |            4659 |                  1 |                      1 | True           |
| GBPUSD   |            8586 |            8586 |                  1 |                      1 | True           |
| AUDUSD   |            4130 |            4130 |                  1 |                      1 | True           |
| USDJPY   |            8362 |            8362 |                  1 |                      1 | True           |
| USDCHF   |            4136 |            4136 |                  1 |                      1 | True           |
| USDCAD   |            6159 |            6159 |                  1 |                      1 | True           |

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
| AUDUSD   |       14 |           1 |            1 |         1 |          1 |
| EURUSD   |       14 |           1 |            1 |         1 |          1 |
| GBPUSD   |       14 |           1 |            1 |         1 |          1 |
| USDCAD   |       14 |           1 |            1 |         1 |          1 |
| USDCHF   |       14 |           1 |            1 |         1 |          1 |
| USDJPY   |       14 |           1 |            1 |         1 |          1 |

#### Plots
![stage_06_tick_exact_monthly](../../figures/oco_bible/stage_06_tick_exact_monthly.png)

#### Cross-Symbol Portability (X01-X03)
| family                |   symbols_covered |   mean_across_symbols |   std_across_symbols |   spread_max_min |   x01_all_symbols_positive |
|:----------------------|------------------:|----------------------:|---------------------:|-----------------:|---------------------------:|
| oco_first_touch_clean |                 6 |              4.49316  |            1.34368   |        3.62955   |                        nan |
| oco_first_touch       |                 6 |              0.127387 |            0.0372793 |        0.0999865 |                        nan |

### Auto Snapshot - Stage 06

- generated_at: `2026-04-12 17:21:09 UTC`
- Verifier recomputes OCO outcomes independently from stored labels.
- All summary rates should remain near 1.0 for contract consistency.

#### Key Results
| symbol   |   rows_selected |   rows_verified |   exact_match_rate |   pos_label_match_rate | overall_pass   |
|:---------|----------------:|----------------:|-------------------:|-----------------------:|:---------------|
| EURUSD   |            6386 |            6386 |                  1 |                      1 | True           |
| GBPUSD   |           11624 |           11624 |                  1 |                      1 | True           |
| AUDUSD   |            3666 |            3666 |                  1 |                      1 | True           |
| USDJPY   |            4681 |            4681 |                  1 |                      1 | True           |
| USDCHF   |            3334 |            3334 |                  1 |                      1 | True           |
| USDCAD   |            4065 |            4065 |                  1 |                      1 | True           |

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
| AUDUSD   |       15 |           1 |            1 |         1 |          1 |
| EURUSD   |       15 |           1 |            1 |         1 |          1 |
| GBPUSD   |       15 |           1 |            1 |         1 |          1 |
| USDCAD   |       15 |           1 |            1 |         1 |          1 |
| USDCHF   |       15 |           1 |            1 |         1 |          1 |
| USDJPY   |       14 |           1 |            1 |         1 |          1 |

#### Plots
![stage_06_tick_exact_monthly](../../figures/oco_bible/stage_06_tick_exact_monthly.png)

#### Cross-Symbol Portability (X01-X03)
| family                |   symbols_covered |   mean_across_symbols |   std_across_symbols |   spread_max_min |   x01_all_symbols_positive |
|:----------------------|------------------:|----------------------:|---------------------:|-----------------:|---------------------------:|
| oco_first_touch_clean |                 6 |              3.84634  |              1.08914 |          3.02862 |                        nan |
| oco_first_touch       |                 1 |              0.187709 |            nan       |          0       |                        nan |

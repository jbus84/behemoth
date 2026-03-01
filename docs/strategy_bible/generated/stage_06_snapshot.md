### Auto Snapshot - Stage 06

- generated_at: `2026-03-01 12:47:46 UTC`
- Verifier recomputes OCO outcomes independently from stored labels.
- All summary rates should remain near 1.0 for contract consistency.

#### Key Results
| symbol   |   rows_selected |   rows_verified |   exact_match_rate |   pos_label_match_rate | overall_pass   |
|:---------|----------------:|----------------:|-------------------:|-----------------------:|:---------------|
| EURUSD   |            5903 |            5903 |                  1 |                      1 | True           |
| GBPUSD   |            7767 |            7767 |                  1 |                      1 | True           |
| USDJPY   |           11582 |           11582 |                  1 |                      1 | True           |
| USDCHF   |           36965 |           36965 |                  1 |                      1 | True           |

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
| EURUSD   |        9 |           1 |            1 |         1 |          1 |
| GBPUSD   |        9 |           1 |            1 |         1 |          1 |
| USDCHF   |        9 |           1 |            1 |         1 |          1 |
| USDJPY   |        9 |           1 |            1 |         1 |          1 |

#### Plots
![stage_06_tick_exact_monthly](../../figures/oco_bible/stage_06_tick_exact_monthly.png)

#### Cross-Symbol Portability (X01-X03)
| family                |   symbols_covered |   mean_across_symbols |   std_across_symbols |   spread_max_min |   x01_all_symbols_positive |
|:----------------------|------------------:|----------------------:|---------------------:|-----------------:|---------------------------:|
| oco_first_touch_clean |                 6 |              1.66269  |            0.85245   |         2.36643  |                        nan |
| oco_first_touch       |                 6 |              0.176557 |            0.0590746 |         0.139407 |                        nan |

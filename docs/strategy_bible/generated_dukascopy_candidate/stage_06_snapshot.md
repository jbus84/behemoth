### Auto Snapshot - Stage 06

- generated_at: `2026-03-15 12:55:53 UTC`
- Verifier recomputes OCO outcomes independently from stored labels.
- All summary rates should remain near 1.0 for contract consistency.

#### Key Results
| symbol   |   rows_selected |   rows_verified |   exact_match_rate |   pos_label_match_rate | overall_pass   |
|:---------|----------------:|----------------:|-------------------:|-----------------------:|:---------------|
| EURUSD   |            4351 |            4351 |                  1 |                      1 | True           |
| GBPUSD   |           14622 |           14622 |                  1 |                      1 | True           |
| USDJPY   |           27826 |           27826 |                  1 |                      1 | True           |
| USDCHF   |            3676 |            3676 |                  1 |                      1 | True           |
| AUDUSD   |            9724 |            9724 |                  1 |                      1 | True           |
| USDCAD   |            5504 |            5504 |                  1 |                      1 | True           |

#### Interpretation Notes
- Verifier recomputes OCO outcomes independently from stored labels.
- All summary rates should remain near 1.0 for contract consistency.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Cross-Symbol Portability (X01-X03)
| family                |   symbols_covered |   mean_across_symbols |   std_across_symbols |   spread_max_min |   x01_all_symbols_positive |
|:----------------------|------------------:|----------------------:|---------------------:|-----------------:|---------------------------:|
| oco_first_touch_clean |                 6 |              4.52626  |             1.38226  |         3.7677   |                        nan |
| oco_first_touch       |                 6 |              0.190727 |             0.053507 |         0.132186 |                        nan |

### Auto Snapshot - Stage 12

- generated_at: `2026-04-12 17:21:09 UTC`
- Stage 12 is a hard gate: strict signal parity and execution parity must both match reduced-core truth.
- Any non-green Stage 12 symbol is a critical deployment blocker.

#### Key Results
| symbol   | signal_parity_pass   | execution_parity_pass   | api_parity_pass   |   selected_missing_expected |   selected_extra_runtime |   execution_failed_checks_high_critical | verdict   | report_path                                       |
|:---------|:---------------------|:------------------------|:------------------|----------------------------:|-------------------------:|----------------------------------------:|:----------|:--------------------------------------------------|
| EURUSD   | False                | False                   | False             |                           1 |                        1 |                                       1 | red       | docs/analysis/EURUSD_stage12_api_parity_report.md |
| GBPUSD   | False                | False                   | False             |                           1 |                        1 |                                       1 | red       | docs/analysis/GBPUSD_stage12_api_parity_report.md |
| AUDUSD   | False                | False                   | False             |                           1 |                        1 |                                       1 | red       | docs/analysis/AUDUSD_stage12_api_parity_report.md |
| USDJPY   | False                | False                   | False             |                           1 |                        1 |                                       1 | red       | docs/analysis/USDJPY_stage12_api_parity_report.md |
| USDCHF   | False                | False                   | False             |                           1 |                        1 |                                       1 | red       | docs/analysis/USDCHF_stage12_api_parity_report.md |
| USDCAD   | False                | False                   | False             |                           1 |                        1 |                                       1 | red       | docs/analysis/USDCAD_stage12_api_parity_report.md |

#### Interpretation Notes
- Stage 12 is a hard gate: strict signal parity and execution parity must both match reduced-core truth.
- Any non-green Stage 12 symbol is a critical deployment blocker.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Plots
![stage_12_api_parity_gate_matrix](../../figures/oco_bible/stage_12_api_parity_gate_matrix.png)

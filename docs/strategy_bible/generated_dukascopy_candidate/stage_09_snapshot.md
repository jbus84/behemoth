### Auto Snapshot - Stage 09

- generated_at: `2026-03-15 12:55:53 UTC`
- Governance snapshot combines symbol gate matrix with artifact inventory completeness.
- Missing required artifacts: 0.

#### Key Results
| symbol   | gate_reduced_lb95_month_gt0   | gate_tick_exact   | gate_robust_lb95_trade_gt0   | gate_robust_months_majority   | gate_api_signal_parity   | gate_api_execution_parity   | gate_api_parity   | symbol_all_gates_pass   |
|:---------|:------------------------------|:------------------|:-----------------------------|:------------------------------|:-------------------------|:----------------------------|:------------------|:------------------------|
| EURUSD   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |
| GBPUSD   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |
| USDJPY   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |
| USDCHF   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |
| AUDUSD   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |
| USDCAD   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |

#### Interpretation Notes
- Governance snapshot combines symbol gate matrix with artifact inventory completeness.
- Missing required artifacts: 0.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Plots
![stage_09_gate_matrix](../../figures/oco_bible/stage_09_gate_matrix.png)
![stage_09_predeploy_checks](../../figures/oco_bible/stage_09_predeploy_checks.png)

#### Predeploy Validator Status
| symbol   | status   | blocker   |   checks_total |   checks_failed |   leakage_high_critical_issues |   execution_risk_high_critical_issues |   g01_near_fail_count |   g03_lock_drift_flags | as_of      | window_end   | failed_checks   |
|:---------|:---------|:----------|---------------:|----------------:|-------------------------------:|--------------------------------------:|----------------------:|-----------------------:|:-----------|:-------------|:----------------|
| EURUSD   | pass     | False     |             27 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-03-15 | 2026-04-17   |                 |
| GBPUSD   | pass     | False     |             27 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-03-15 | 2026-04-17   |                 |
| USDJPY   | pass     | False     |             27 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-03-15 | 2026-04-17   |                 |
| USDCHF   | pass     | False     |             27 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-03-15 | 2026-04-17   |                 |
| AUDUSD   | pass     | False     |             27 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-03-15 | 2026-04-17   |                 |
| USDCAD   | pass     | False     |             27 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-03-15 | 2026-04-17   |                 |

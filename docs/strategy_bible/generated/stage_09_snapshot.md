### Auto Snapshot - Stage 09

- generated_at: `2026-03-30 10:10:58 UTC`
- Governance snapshot combines symbol gate matrix with artifact inventory completeness.
- Missing required artifacts: 0.

#### Authority Note
- Authority label: `generated truth snapshot`
- Authoritative for: current Stage 09 governance gate state, predeploy completeness, and symbol-level blocker visibility.
- Not authoritative for: operator prioritization, remediation narrative, or cross-stage interpretation beyond the generated checks.
- Depends on: the strategy bible build process, current governance predeploy artifacts, and required artifact inventory checks.

#### Key Results
| symbol   | gate_reduced_lb95_month_gt0   | gate_tick_exact   | gate_robust_lb95_trade_gt0   | gate_robust_months_majority   | gate_api_signal_parity   | gate_api_execution_parity   | gate_api_parity   | symbol_all_gates_pass   |
|:---------|:------------------------------|:------------------|:-----------------------------|:------------------------------|:-------------------------|:----------------------------|:------------------|:------------------------|
| EURUSD   | True                          | True              | True                         | True                          | True                     | True                        | True              | True                    |
| GBPUSD   | True                          | True              | True                         | True                          | True                     | True                        | True              | True                    |
| AUDUSD   | True                          | True              | True                         | True                          | True                     | True                        | True              | True                    |
| USDJPY   | True                          | True              | True                         | True                          | True                     | True                        | True              | True                    |
| USDCHF   | True                          | True              | True                         | True                          | True                     | True                        | True              | True                    |
| USDCAD   | True                          | True              | True                         | True                          | True                     | True                        | True              | True                    |

#### Interpretation Notes
- Governance snapshot combines symbol gate matrix with artifact inventory completeness.
- Missing required artifacts: 0.

#### Action Trigger Summary
| symbol   | metric_id            | band   | severity   | action_code   | action_summary     | owner      |
|:---------|:---------------------|:-------|:-----------|:--------------|:-------------------|:-----------|
| AUDUSD   | G01_near_fail_count  | green  | info       | A0_MONITOR    | within policy band | governance |
| AUDUSD   | G03_lock_drift_flags | green  | info       | A0_MONITOR    | within policy band | governance |
| EURUSD   | G01_near_fail_count  | green  | info       | A0_MONITOR    | within policy band | governance |
| EURUSD   | G03_lock_drift_flags | green  | info       | A0_MONITOR    | within policy band | governance |
| GBPUSD   | G01_near_fail_count  | green  | info       | A0_MONITOR    | within policy band | governance |
| GBPUSD   | G03_lock_drift_flags | green  | info       | A0_MONITOR    | within policy band | governance |
| USDCAD   | G01_near_fail_count  | green  | info       | A0_MONITOR    | within policy band | governance |
| USDCAD   | G03_lock_drift_flags | green  | info       | A0_MONITOR    | within policy band | governance |
| USDCHF   | G01_near_fail_count  | green  | info       | A0_MONITOR    | within policy band | governance |
| USDCHF   | G03_lock_drift_flags | green  | info       | A0_MONITOR    | within policy band | governance |
| USDJPY   | G01_near_fail_count  | green  | info       | A0_MONITOR    | within policy band | governance |
| USDJPY   | G03_lock_drift_flags | green  | info       | A0_MONITOR    | within policy band | governance |

#### Plots
![stage_09_gate_matrix](../../figures/oco_bible/stage_09_gate_matrix.png)
![stage_09_predeploy_checks](../../figures/oco_bible/stage_09_predeploy_checks.png)

#### Predeploy Validator Status
| symbol   | status   | blocker   |   checks_total |   checks_failed |   leakage_high_critical_issues |   execution_risk_high_critical_issues |   g01_near_fail_count |   g03_lock_drift_flags | as_of      | window_end   | failed_checks   |
|:---------|:---------|:----------|---------------:|----------------:|-------------------------------:|--------------------------------------:|----------------------:|-----------------------:|:-----------|:-------------|:----------------|
| EURUSD   | pass     | False     |             25 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-02-26 | 2026-03-31   |                 |
| GBPUSD   | pass     | False     |             25 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-02-26 | 2026-03-31   |                 |
| AUDUSD   | pass     | False     |             36 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-03-05 | 2026-04-07   |                 |
| USDJPY   | pass     | False     |             25 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-02-26 | 2026-03-31   |                 |
| USDCHF   | pass     | False     |             36 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-03-05 | 2026-04-07   |                 |
| USDCAD   | pass     | False     |             36 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-03-05 | 2026-04-07   |                 |

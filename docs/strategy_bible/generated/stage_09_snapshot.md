### Auto Snapshot - Stage 09

- generated_at: `2026-02-27 13:24:04 UTC`
- Governance snapshot combines symbol gate matrix with artifact inventory completeness.
- Missing required artifacts: 0.

#### Key Results
| symbol   | gate_reduced_lb95_month_gt0   | gate_tick_exact   | gate_robust_lb95_trade_gt0   | gate_robust_months_majority   | symbol_all_gates_pass   |
|:---------|:------------------------------|:------------------|:-----------------------------|:------------------------------|:------------------------|
| EURUSD   | True                          | True              | True                         | True                          | True                    |
| GBPUSD   | True                          | True              | True                         | True                          | True                    |
| USDJPY   | True                          | True              | True                         | True                          | True                    |

#### Plots
![stage_09_gate_matrix](../../figures/oco_bible/stage_09_gate_matrix.png)
![stage_09_predeploy_checks](../../figures/oco_bible/stage_09_predeploy_checks.png)

#### Predeploy Validator Status
| symbol   | status   | blocker   |   checks_total |   checks_failed |   leakage_high_critical_issues |   execution_risk_high_critical_issues |   g01_near_fail_count |   g03_lock_drift_flags | as_of      | window_end   | failed_checks   |
|:---------|:---------|:----------|---------------:|----------------:|-------------------------------:|--------------------------------------:|----------------------:|-----------------------:|:-----------|:-------------|:----------------|
| EURUSD   | pass     | False     |             25 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-02-26 | 2026-03-31   |                 |
| GBPUSD   | pass     | False     |             25 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-02-26 | 2026-03-31   |                 |
| USDJPY   | pass     | False     |             25 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-02-26 | 2026-03-31   |                 |

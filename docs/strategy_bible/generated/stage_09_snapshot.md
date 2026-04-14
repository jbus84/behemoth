### Auto Snapshot - Stage 09

- generated_at: `2026-04-12 17:21:09 UTC`
- Governance snapshot combines symbol gate matrix with artifact inventory completeness.
- Missing required artifacts: 2.

#### Authority Note
- Authority label: `generated truth snapshot`
- Authoritative for: current Stage 09 governance gate state, predeploy completeness, and symbol-level blocker visibility.
- Not authoritative for: operator prioritization, remediation narrative, or cross-stage interpretation beyond the generated checks.
- Depends on: the strategy bible build process, current governance predeploy artifacts, and required artifact inventory checks.

#### Key Results
| symbol   | gate_reduced_lb95_month_gt0   | gate_tick_exact   | gate_robust_lb95_trade_gt0   | gate_robust_months_majority   | gate_api_signal_parity   | gate_api_execution_parity   | gate_api_parity   | symbol_all_gates_pass   |
|:---------|:------------------------------|:------------------|:-----------------------------|:------------------------------|:-------------------------|:----------------------------|:------------------|:------------------------|
| EURUSD   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |
| GBPUSD   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |
| AUDUSD   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |
| USDJPY   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |
| USDCHF   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |
| USDCAD   | True                          | True              | True                         | True                          | False                    | False                       | False             | False                   |

#### Interpretation Notes
- Governance snapshot combines symbol gate matrix with artifact inventory completeness.
- Missing required artifacts: 2.

#### Action Trigger Summary
| symbol   | metric_id            | band   | severity   | action_code   | action_summary                      | owner      |
|:---------|:---------------------|:-------|:-----------|:--------------|:------------------------------------|:-----------|
| AUDUSD   | G01_near_fail_count  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| AUDUSD   | G03_lock_drift_flags | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| EURUSD   | G01_near_fail_count  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| EURUSD   | G03_lock_drift_flags | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| GBPUSD   | G01_near_fail_count  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| GBPUSD   | G03_lock_drift_flags | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| USDCAD   | G01_near_fail_count  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| USDCAD   | G03_lock_drift_flags | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| USDCHF   | G01_near_fail_count  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| USDCHF   | G03_lock_drift_flags | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| USDJPY   | G01_near_fail_count  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| USDJPY   | G03_lock_drift_flags | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |

#### Details
| group   | symbol   | artifact   | path                                                                                     |
|:--------|:---------|:-----------|:-----------------------------------------------------------------------------------------|
| audit   | ALL      | checks_csv | configs/research/docs/data/analysis/tick_opportunity_mining/oco_logical_audit_checks.csv |
| audit   | ALL      | issues_csv | configs/research/docs/data/analysis/tick_opportunity_mining/oco_logical_audit_issues.csv |

#### Plots
![stage_09_gate_matrix](../../figures/oco_bible/stage_09_gate_matrix.png)
![stage_09_predeploy_checks](../../figures/oco_bible/stage_09_predeploy_checks.png)

#### Predeploy Validator Status
| symbol   | status   | blocker   |   checks_total |   checks_failed |   leakage_high_critical_issues |   execution_risk_high_critical_issues | failed_checks          |
|:---------|:---------|:----------|---------------:|----------------:|-------------------------------:|--------------------------------------:|:-----------------------|
| EURUSD   | missing  | True      |              1 |               1 |                              0 |                                     0 | missing_predeploy_json |
| GBPUSD   | missing  | True      |              1 |               1 |                              0 |                                     0 | missing_predeploy_json |
| AUDUSD   | missing  | True      |              1 |               1 |                              0 |                                     0 | missing_predeploy_json |
| USDJPY   | missing  | True      |              1 |               1 |                              0 |                                     0 | missing_predeploy_json |
| USDCHF   | missing  | True      |              1 |               1 |                              0 |                                     0 | missing_predeploy_json |
| USDCAD   | missing  | True      |              1 |               1 |                              0 |                                     0 | missing_predeploy_json |

- Missing predeploy JSON for one or more symbols. Generate with `scripts/validate_oco_live_governance.py --mode deploy --data-reliability-checks-csv ... --leakage-checks-csv ... --execution-risk-checks-csv ... --out-json ...` per symbol.

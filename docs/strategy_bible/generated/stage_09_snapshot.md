### Auto Snapshot - Stage 09

- generated_at: `2026-03-03 12:43:04 UTC`
- Governance snapshot combines symbol gate matrix with artifact inventory completeness.
- Missing required artifacts: 4.

#### Key Results
| symbol   |   gate_reduced_lb95_month_gt0 |   gate_tick_exact |   gate_robust_lb95_trade_gt0 |   gate_robust_months_majority | symbol_all_gates_pass   |
|:---------|------------------------------:|------------------:|-----------------------------:|------------------------------:|:------------------------|
| EURUSD   |                             0 |                 1 |                            1 |                             1 | False                   |
| GBPUSD   |                             1 |                 1 |                            1 |                             1 | True                    |
| AUDUSD   |                           nan |               nan |                          nan |                           nan | False                   |
| USDJPY   |                             1 |                 1 |                            1 |                             1 | True                    |
| USDCHF   |                             1 |                 1 |                            1 |                             1 | True                    |
| USDCAD   |                           nan |               nan |                          nan |                           nan | False                   |

#### Interpretation Notes
- Governance snapshot combines symbol gate matrix with artifact inventory completeness.
- Missing required artifacts: 4.

#### Action Trigger Summary
| symbol   | metric_id            | band   | severity   | action_code   | action_summary                      | owner      |
|:---------|:---------------------|:-------|:-----------|:--------------|:------------------------------------|:-----------|
| AUDUSD   | G01_near_fail_count  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| AUDUSD   | G03_lock_drift_flags | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| EURUSD   | G01_near_fail_count  | green  | info       | A0_MONITOR    | within policy band                  | governance |
| EURUSD   | G03_lock_drift_flags | green  | info       | A0_MONITOR    | within policy band                  | governance |
| GBPUSD   | G01_near_fail_count  | green  | info       | A0_MONITOR    | within policy band                  | governance |
| GBPUSD   | G03_lock_drift_flags | green  | info       | A0_MONITOR    | within policy band                  | governance |
| USDCAD   | G01_near_fail_count  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| USDCAD   | G03_lock_drift_flags | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | governance |
| USDCHF   | G01_near_fail_count  | green  | info       | A0_MONITOR    | within policy band                  | governance |
| USDCHF   | G03_lock_drift_flags | green  | info       | A0_MONITOR    | within policy band                  | governance |
| USDJPY   | G01_near_fail_count  | green  | info       | A0_MONITOR    | within policy band                  | governance |
| USDJPY   | G03_lock_drift_flags | green  | info       | A0_MONITOR    | within policy band                  | governance |

#### Details
| group   | symbol   | artifact               | path                                                                                                               |
|:--------|:---------|:-----------------------|:-------------------------------------------------------------------------------------------------------------------|
| symbol  | AUDUSD   | tick_exact_report_md   | configs/research/docs/docs/analysis/audusd_oco_tick_exact_rolling_report.md                                        |
| symbol  | AUDUSD   | tick_exact_summary_csv | configs/research/docs/data/analysis/tick_opportunity_mining/reduced_core_rolling/AUDUSD_oco_tick_exact_summary.csv |
| symbol  | USDCAD   | tick_exact_report_md   | configs/research/docs/docs/analysis/usdcad_oco_tick_exact_rolling_report.md                                        |
| symbol  | USDCAD   | tick_exact_summary_csv | configs/research/docs/data/analysis/tick_opportunity_mining/reduced_core_rolling/USDCAD_oco_tick_exact_summary.csv |

#### Plots
![stage_09_gate_matrix](../../figures/oco_bible/stage_09_gate_matrix.png)
![stage_09_predeploy_checks](../../figures/oco_bible/stage_09_predeploy_checks.png)

#### Predeploy Validator Status
| symbol   | status   | blocker   |   checks_total |   checks_failed |   leakage_high_critical_issues |   execution_risk_high_critical_issues |   g01_near_fail_count |   g03_lock_drift_flags | as_of      | window_end   | failed_checks                                                                  |
|:---------|:---------|:----------|---------------:|----------------:|-------------------------------:|--------------------------------------:|----------------------:|-----------------------:|:-----------|:-------------|:-------------------------------------------------------------------------------|
| EURUSD   | pass     | False     |             25 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-02-26 | 2026-03-31   |                                                                                |
| GBPUSD   | pass     | False     |             25 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-02-26 | 2026-03-31   |                                                                                |
| AUDUSD   | missing  | True      |              1 |               1 |                              0 |                                     0 |                   nan |                    nan | nan        | nan          | missing_predeploy_json                                                         |
| USDJPY   | pass     | False     |             25 |               0 |                              0 |                                     0 |                     0 |                      0 | 2026-02-26 | 2026-03-31   |                                                                                |
| USDCHF   | fail     | True      |             19 |               3 |                              0 |                                     0 |                     0 |                      0 | 2026-02-28 | 2026-04-02   | data_reliability_rows_present,leakage_rows_present,execution_risk_rows_present |
| USDCAD   | missing  | True      |              1 |               1 |                              1 |                                     0 |                   nan |                    nan | nan        | nan          | missing_predeploy_json                                                         |

- Missing predeploy JSON for one or more symbols. Generate with `scripts/validate_oco_live_governance.py --mode deploy --data-reliability-checks-csv ... --leakage-checks-csv ... --execution-risk-checks-csv ... --out-json ...` per symbol.

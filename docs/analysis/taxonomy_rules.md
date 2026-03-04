# Analysis Taxonomy Rules

- generated_at_utc: `2026-03-04T07:32:08Z`

## Group Assignment Order
1. `core`: canonical governance reports for the OCO bible.
2. `symbol`: filename maps to specific symbol token (`EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`, `USDCAD`).
3. `stage`: filename keyword maps to stage id.
4. `legacy`: known historical/legacy analysis families.
5. `unclassified`: everything else (should be zero in healthy state).

## Stage Keyword Map
|   stage_id | keywords                                                                  |
|-----------:|:--------------------------------------------------------------------------|
|          1 | data_reliability                                                          |
|          2 | mining, opportunity_mining                                                |
|          3 | monthly_wfo, _wfo_, threshold_sensitivity                                 |
|          4 | stop_limit, execution_risk, execution_drift                               |
|          5 | reduced_core, rule_universe_registry                                      |
|          6 | tick_exact                                                                |
|          7 | logical_audit                                                             |
|          8 | robustness, remediation_metric_decomposition                              |
|          9 | governance, live_governance, alert_remediation, governance_explainability |
|         10 | risk, checklist, stage_integrity                                          |
|         11 | execution_monte_carlo                                                     |

## Legacy Keyword Map
| keyword              |
|:---------------------|
| close_path_contracts |
| cluster_earlywarning |
| kf_directional       |
| mom_loss_limiter     |
| m5_mom_m15_momrev    |

## Core Report Set
| doc_path                                                |
|:--------------------------------------------------------|
| analysis/data_reliability_report.md                     |
| analysis/oco_alert_remediation_report.md                |
| analysis/oco_docs_contract_report.md                    |
| analysis/oco_edge_clarity_report.md                     |
| analysis/oco_execution_drift_report.md                  |
| analysis/oco_execution_monte_carlo_report.md            |
| analysis/oco_execution_monte_carlo_validation_report.md |
| analysis/oco_execution_risk_prelive_report.md           |
| analysis/oco_governance_explainability_report.md        |
| analysis/oco_leakage_integrity_report.md                |
| analysis/oco_logical_audit_report.md                    |
| analysis/oco_rule_universe_registry_report.md           |
| analysis/oco_stage_integrity_report.md                  |
| analysis/oco_threshold_sensitivity_report.md            |
| analysis/operator_action_report.md                      |
| analysis/run_delta_dashboard.md                         |
| analysis/taxonomy_rules.md                              |
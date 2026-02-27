# Analysis Taxonomy Rules

- generated_at_utc: `2026-02-27T11:40:39Z`

## Group Assignment Order
1. `archive`: any document under `docs/archive/`.
2. `core`: canonical governance reports for the OCO bible.
3. `symbol`: filename maps to specific symbol token (`EURUSD`, `GBPUSD`, `USDJPY`).
4. `stage`: filename keyword maps to stage id.
5. `legacy`: known historical/legacy analysis families.
6. `unclassified`: everything else (should be zero in healthy state).

## Stage Keyword Map
|   stage_id | keywords                                     |
|-----------:|:---------------------------------------------|
|          1 | data_reliability                             |
|          2 | mining, opportunity_mining                   |
|          3 | monthly_wfo, _wfo_                           |
|          4 | stop_limit, execution_risk                   |
|          5 | reduced_core                                 |
|          6 | tick_exact                                   |
|          7 | logical_audit                                |
|          8 | robustness, remediation_metric_decomposition |
|          9 | governance, live_governance                  |
|         10 | risk, checklist                              |
|         11 | execution_monte_carlo                        |

## Legacy Keyword Map
| keyword                |
|:-----------------------|
| close_path_contracts   |
| cluster_earlywarning   |
| kf_directional         |
| mom_loss_limiter       |
| m5_mom_m15_momrev      |
| stable_pairs_whitelist |

## Core Report Set
| doc_path                                                |
|:--------------------------------------------------------|
| analysis/data_reliability_report.md                     |
| analysis/oco_docs_contract_report.md                    |
| analysis/oco_edge_clarity_report.md                     |
| analysis/oco_execution_monte_carlo_report.md            |
| analysis/oco_execution_monte_carlo_validation_report.md |
| analysis/oco_execution_risk_prelive_report.md           |
| analysis/oco_leakage_integrity_report.md                |
| analysis/oco_logical_audit_report.md                    |
| analysis/operator_action_report.md                      |
| analysis/run_delta_dashboard.md                         |
| analysis/taxonomy_rules.md                              |
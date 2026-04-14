# Analysis Taxonomy Rules

- generated_at_utc: `2026-04-12T17:19:19Z`

## Group Assignment Order
1. `archive`: anything already stored below `docs/archive/`.
2. `core`: canonical governance reports for the OCO bible.
3. `candidate`: experimental, offset-robustness, and candidate-labelled analysis artifacts that should stay visible but outside the live centerline.
4. `compatibility`: cTrader, HistData, FTMO, and reconciliation-oriented surfaces.
5. `symbol`: filename maps to specific symbol token (`EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`, `USDCAD`).
6. `stage`: filename keyword maps to stage id.
7. `legacy`: known historical/legacy analysis families.
8. `unclassified`: everything else (should be zero in healthy state).

## Stage Keyword Map
|   stage_id | keywords                                                                                                                                                                                    |
|-----------:|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|          1 | data_reliability                                                                                                                                                                            |
|          2 | mining, opportunity_mining, ml_ready                                                                                                                                                        |
|          3 | monthly_wfo, _wfo_, threshold_sensitivity                                                                                                                                                   |
|          4 | stop_limit, execution_risk, execution_drift                                                                                                                                                 |
|          5 | reduced_core, rule_universe_registry                                                                                                                                                        |
|          6 | tick_exact                                                                                                                                                                                  |
|          7 | logical_audit                                                                                                                                                                               |
|          8 | robustness, remediation_metric_decomposition                                                                                                                                                |
|          9 | governance, live_governance, alert_remediation, governance_explainability                                                                                                                   |
|         10 | risk, checklist, stage_integrity                                                                                                                                                            |
|         11 | execution_monte_carlo                                                                                                                                                                       |
|         12 | stage12, api_parity, ab_parity, ctrader_ab_parity, reconciliation, runtime_db, tick_forensics, histdata_vs_ctrader, histdata_testclient_execution_parity, histdata_ctrader_execution_parity |
|         13 | stage13, dukascopy_testclient                                                                                                                                                               |
|         14 | stage14, jforex_runtime                                                                                                                                                                     |
|          8 | offset_tickbar_robustness, offset_robustness, warmup_sensitivity, api_offset_confirmation                                                                                                   |
|         13 | stage13, dukascopy_testclient                                                                                                                                                               |
|         14 | stage14, jforex_runtime_certification, jforex_live                                                                                                                                          |

## Candidate Keyword Map
| keyword                   |
|:--------------------------|
| candidate                 |
| offset_tickbar_robustness |
| brainstorm                |

## Compatibility Keyword Map
| keyword                     |
|:----------------------------|
| api_parity                  |
| ctrader                     |
| histdata                    |
| reconciliation              |
| runtime_db                  |
| tick_forensics              |
| testclient_execution_parity |
| ftmo_                       |

## Legacy Keyword Map
| keyword              |
|:---------------------|
| close_path_contracts |
| cluster_earlywarning |
| kf_directional       |
| mom_loss_limiter     |
| m5_mom_m15_momrev    |

## Core Report Set
| doc_path                                                        |
|:----------------------------------------------------------------|
| analysis/2026-03-23-live-launch-brainstorm.md                   |
| analysis/AUDUSD_dukascopy_testclient_execution_parity_report.md |
| analysis/AUDUSD_histdata_testclient_execution_parity_report.md  |
| analysis/AUDUSD_stage12_api_parity_report.md                    |
| analysis/EURUSD_testclient_execution_parity_report.md           |
| analysis/EURUSD_testclient_execution_parity_tolerant_report.md  |
| analysis/GBPUSD_dukascopy_testclient_execution_parity_report.md |
| analysis/GBPUSD_histdata_testclient_execution_parity_report.md  |
| analysis/GBPUSD_stage12_api_parity_report.md                    |
| analysis/USDCAD_dukascopy_testclient_execution_parity_report.md |
| analysis/USDCAD_histdata_testclient_execution_parity_report.md  |
| analysis/USDCAD_stage12_api_parity_report.md                    |
| analysis/USDCHF_dukascopy_testclient_execution_parity_report.md |
| analysis/USDCHF_histdata_testclient_execution_parity_report.md  |
| analysis/USDCHF_stage12_api_parity_report.md                    |
| analysis/USDJPY_dukascopy_testclient_execution_parity_report.md |
| analysis/USDJPY_histdata_testclient_execution_parity_report.md  |
| analysis/USDJPY_stage12_api_parity_report.md                    |
| analysis/data_reliability_report.md                             |
| analysis/dukascopy_source_completeness_report.md                |
| analysis/eurusd_dukascopy_vs_histdata_tick_similarity_report.md |
| analysis/local_jforex_surrogate_report.md                       |
| analysis/oco_alert_remediation_report.md                        |
| analysis/oco_docs_contract_report.md                            |
| analysis/oco_edge_clarity_report.md                             |
| analysis/oco_execution_drift_report.md                          |
| analysis/oco_execution_monte_carlo_report.md                    |
| analysis/oco_execution_monte_carlo_validation_report.md         |
| analysis/oco_execution_risk_prelive_report.md                   |
| analysis/oco_governance_explainability_report.md                |
| analysis/oco_leakage_integrity_report.md                        |
| analysis/oco_logical_audit_report.md                            |
| analysis/oco_rule_universe_registry_report.md                   |
| analysis/oco_stage_integrity_report.md                          |
| analysis/oco_threshold_sensitivity_report.md                    |
| analysis/operator_action_report.md                              |
| analysis/run_delta_dashboard.md                                 |
| analysis/stage13_dukascopy_testclient_report.md                 |
| analysis/stage14_jforex_runtime_certification_report.md         |
| analysis/taxonomy_rules.md                                      |
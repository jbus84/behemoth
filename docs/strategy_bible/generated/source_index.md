# Source Index

## Scripts
- `scripts/audit_data_reliability.py`
- `scripts/audit_oco_leakage_label_integrity.py`
- `scripts/audit_oco_execution_risk_prelive.py`
- `scripts/run_tick_opportunity_mining.py`
- `scripts/run_tick_opportunity_monthly_wfo.py`
- `scripts/analyze_oco_stop_limit_tickfill.py`
- `scripts/select_oco_reduced_core_rolling.py`
- `scripts/verify_oco_tick_exact_shortlist.py`
- `scripts/analyze_oco_monthly_wfo_robustness.py`
- `scripts/audit_oco_pipeline_logical_issues.py`
- `scripts/validate_oco_docs_contract.py`
- `scripts/build_oco_strategy_bible.py`
- `scripts/build_docs_catalog.py`
- `scripts/check_oco_docs_stage_integrity.py`
- `scripts/validate_oco_rule_universe_registry.py`
- `scripts/build_oco_execution_drift_report.py`
- `scripts/remediate_oco_monitoring_alerts.py`
- `scripts/build_oco_governance_explainability_report.py`
- `scripts/build_oco_threshold_sensitivity_report.py`
- `scripts/register_docs_run.py`
- `scripts/build_run_delta_dashboard.py`
- `scripts/build_operator_action_report.py`
- `scripts/run_execution_monte_carlo.py`
- `scripts/validate_execution_monte_carlo.py`

## Configs
- `configs/research/experiments/eurusd_tick_opportunity_mining.yaml`
- `configs/research/experiments/gbpusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml`
- `configs/research/experiments/usdjpy_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml`
- `configs/research/experiments/usdchf_tick_opportunity_mining.yaml`
- `configs/research/experiments/usdchf_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml`
- `configs/research/experiments/eurusd_oco_reduced_core_rolling_2025.yaml`
- `configs/research/experiments/gbpusd_oco_reduced_core_2025.yaml`
- `configs/research/experiments/usdjpy_oco_reduced_core_rolling_2025.yaml`
- `configs/research/experiments/usdchf_oco_reduced_core_rolling_2025.yaml`
- `configs/research/experiments/audusd_tick_opportunity_mining.yaml`
- `configs/research/experiments/audusd_tick_opportunity_ml_dataset.yaml`
- `configs/research/experiments/audusd_tick_opportunity_monthly_wfo_2025.yaml`
- `configs/research/experiments/audusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml`
- `configs/research/experiments/audusd_oco_reduced_core_rolling_2025.yaml`
- `configs/research/docs/oco_bible_manifest.yaml`
- `configs/research/governance/oco_rule_universe_registry.yaml`
- `configs/research/governance/oco_monitoring_exceptions.yaml`

## Tests
- `tests/test_data_reliability_audit.py`
- `tests/test_oco_leakage_label_integrity.py`
- `tests/test_oco_execution_risk_prelive.py`
- `tests/test_tick_opportunity_mining.py`
- `tests/test_oco_reduced_core_rolling.py`
- `tests/test_oco_pipeline_logical_audit.py`
- `tests/test_oco_docs_contract.py`
- `tests/test_build_docs_catalog.py`
- `tests/test_stage_integrity_gate.py`
- `tests/test_validate_oco_rule_universe_registry.py`
- `tests/test_execution_drift_report.py`
- `tests/test_remediate_oco_monitoring_alerts.py`
- `tests/test_governance_explainability_report.py`
- `tests/test_threshold_sensitivity_report.py`
- `tests/test_register_docs_run.py`
- `tests/test_build_run_delta_dashboard.py`
- `tests/test_build_operator_action_report.py`
- `tests/test_execution_monte_carlo.py`
- `tests/test_validate_execution_monte_carlo.py`

## Symbol Reports
### EURUSD
- `docs/analysis/eurusd_tick_opportunity_mining_report.md`
- `docs/analysis/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/eurusd_oco_reduced_core_rolling_report.md`
- `docs/analysis/eurusd_oco_tick_exact_rolling_report.md`
- `docs/analysis/EURUSD_stage12_api_parity_report.md`

### GBPUSD
- `docs/analysis/gbpusd_tick_opportunity_mining_report.md`
- `docs/analysis/gbpusd_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/gbpusd_oco_reduced_core_rolling_report.md`
- `docs/analysis/gbpusd_oco_tick_exact_rolling_report.md`
- `docs/analysis/GBPUSD_stage12_api_parity_report.md`

### AUDUSD
- `docs/analysis/audusd_tick_opportunity_mining_report.md`
- `docs/analysis/audusd_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/audusd_oco_reduced_core_rolling_report.md`
- `docs/analysis/audusd_oco_tick_exact_rolling_report.md`
- `docs/analysis/AUDUSD_stage12_api_parity_report.md`

### USDJPY
- `docs/analysis/usdjpy_tick_opportunity_mining_report.md`
- `docs/analysis/usdjpy_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/usdjpy_oco_reduced_core_rolling_report.md`
- `docs/analysis/usdjpy_oco_tick_exact_rolling_report.md`
- `docs/analysis/USDJPY_stage12_api_parity_report.md`

### USDCHF
- `docs/analysis/usdchf_tick_opportunity_mining_report.md`
- `docs/analysis/usdchf_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/usdchf_oco_reduced_core_rolling_report.md`
- `docs/analysis/usdchf_oco_tick_exact_rolling_report.md`
- `docs/analysis/USDCHF_stage12_api_parity_report.md`

### USDCAD
- `docs/analysis/usdcad_tick_opportunity_mining_report.md`
- `docs/analysis/usdcad_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/usdcad_oco_reduced_core_rolling_report.md`
- `docs/analysis/usdcad_oco_tick_exact_rolling_report.md`
- `docs/analysis/USDCAD_stage12_api_parity_report.md`

## Generated Stage Snapshots
- `docs/strategy_bible/generated/stage_01_snapshot.md`
- `docs/strategy_bible/generated/stage_02_snapshot.md`
- `docs/strategy_bible/generated/stage_03_snapshot.md`
- `docs/strategy_bible/generated/stage_04_snapshot.md`
- `docs/strategy_bible/generated/stage_05_snapshot.md`
- `docs/strategy_bible/generated/stage_06_snapshot.md`
- `docs/strategy_bible/generated/stage_07_snapshot.md`
- `docs/strategy_bible/generated/stage_08_snapshot.md`
- `docs/strategy_bible/generated/stage_09_snapshot.md`
- `docs/strategy_bible/generated/stage_10_snapshot.md`
- `docs/strategy_bible/generated/stage_11_snapshot.md`
- `docs/strategy_bible/generated/stage_12_snapshot.md`

## Stage Metrics
- `data/analysis/tick_opportunity_mining/oco_bible_stage_metrics.csv`
.DEFAULT_GOAL := help
COLOR_RESET := \033[0m
COLOR_HEADER := \033[1;36m
COLOR_SECTION := \033[1;35m
COLOR_TARGET := \033[0;32m
COLOR_DOC := \033[0;34m
COLOR_DESC := \033[2m

# Active symbol list — single source of truth for multi-symbol targets
REBUILD_SYMBOLS := EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD
CTRADER_ROBOT_DST := ~/cAlgo/Sources/Robots/BehemothTradeManager/BehemothTradeManager/BehemothTradeManager.cs
CTRADER_PLUGIN_DST := ~/cAlgo/Sources/Plugins/CustomDataSourceHistDataPlugin/CustomDataSourceHistDataPlugin/CustomDataSourceHistDataPlugin.cs

.PHONY: test docs docs-build docs-contract docs-contract-ci docs-clean precommit-install precommit-run lint format help onboard-symbol check-legacy-drift deploy-cbot deploy-ctrader provision retrain-all rebuild-all quality ty vulture smellcheck radon xenon audit-all freeze-oco freeze-oco-history validate-oco-history reconcile-historical-predictions summarize-runtime-db-run reconcile-ctrader-run export-ctrader-custom-data ctrader-debug-up ctrader-debug-down ctrader-debug-status ctrader-ab-parity-report histdata-ctrader-parity histdata-testclient-parity stage12-api-parity offset-robustness-study offset-frozen-screen

OFFSET_ROBUSTNESS_SYMBOLS_DEFAULT := EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD
OFFSET_ROBUSTNESS_OFFSETS_DEFAULT := 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99
OFFSET_ROBUSTNESS_COARSE_DEFAULT := 0,10,20,30,40,50,60,70,80,90
OFFSET_ROBUSTNESS_API_CONFIRM_DEFAULT := 0,25,50,75
OFFSET_ROBUSTNESS_WARMUP_DEFAULT := 73,145,217,289,400

provision:
	@echo "Provisioning Alertmanager configuration..."
	uv run python scripts/provision_observability.py

test:
	uv run pytest -q

quality: ty lint vulture smellcheck radon xenon
	@echo "\n✅ All quality checks complete"

ty:
	@echo "\n--- Type Checking (ty) ---"
	uv run ty check

vulture:
	@echo "\n--- Dead Code Detection (vulture) ---"
	uv run vulture src/ scripts/ --exclude .venv,data,docs

smellcheck:
	@echo "\n--- Code Smell Detection (smellcheck) ---"
	uv run smellcheck src/

radon:
	@echo "\n--- Cyclomatic Complexity (radon) ---"
	uv run radon cc src/ -s

xenon:
	@echo "\n--- Complexity Enforcement (xenon) ---"
	uv run xenon --max-absolute B --max-modules A src/

onboard-symbol:
	@test -n "$(SYMBOL)" || (echo "error: SYMBOL is required, e.g. make onboard-symbol SYMBOL=USDCAD MONTHS=201801-202602" && exit 1)
	uv run python scripts/onboard_symbol.py --symbol $(SYMBOL) --months $(MONTHS) $(ONBOARD_FLAGS)

retrain-all:
	@echo "══════════════════════════════════════════"
	@echo "  Retraining all symbols (Stages 2-5)    "
	@echo "══════════════════════════════════════════"
	@for sym in $(REBUILD_SYMBOLS); do \
		echo "\n=== Retraining $$sym ==="; \
		uv run python scripts/onboard_symbol.py --symbol $$sym --skip-data --skip-docs --skip-registration --model-export-dir models/oco || exit 1; \
	done
	@echo "\n=== Running Stage-1 data reliability audit (all active symbols) ==="
	uv run python scripts/audit_data_reliability.py \
		--symbols $(shell echo $(REBUILD_SYMBOLS) | sed 's/ /,/g')
	@echo "\n=== Running docs-contract ==="
	$(MAKE) docs-contract
	@echo "\n=== Building mkdocs ==="
	uv run mkdocs build --strict
	@echo "\n✅ Full retrain complete"

rebuild-all:
	@test -n "$(MONTHS)" || (echo "error: MONTHS required, e.g. make rebuild-all MONTHS=201801-202602" && exit 1)
	@echo "══════════════════════════════════════════"
	@echo "  Full rebuild for all symbols (Stages 0-5)"
	@echo "══════════════════════════════════════════"
	@for sym in $(REBUILD_SYMBOLS); do \
		echo "\n=== Rebuilding $$sym ==="; \
		uv run python scripts/onboard_symbol.py --symbol $$sym --months $(MONTHS) --force --skip-docs --skip-registration --model-export-dir models/oco || exit 1; \
	done
	@echo "\n=== Running Stage-1 data reliability audit (all active symbols) ==="
	uv run python scripts/audit_data_reliability.py \
		--symbols $(shell echo $(REBUILD_SYMBOLS) | sed 's/ /,/g')
	@echo "\n=== Running docs-contract ==="
	$(MAKE) docs-contract
	@echo "\n=== Building mkdocs ==="
	uv run mkdocs build --strict
	@echo "\n✅ Full rebuild complete"

deploy-cbot:
	@echo "Deploying BehemothTradeManager.cs to cTrader Robots directory..."
	cp src/cbot/BehemothTradeManager.cs $(CTRADER_ROBOT_DST)
	@echo "Deployment complete! Please rebuild the bot in cTrader Automate."

deploy-ctrader:
	@echo "Deploying BehemothTradeManager.cs to cTrader Robots directory..."
	cp src/cbot/BehemothTradeManager.cs $(CTRADER_ROBOT_DST)
	@echo "Deploying CustomDataSourceHistDataPlugin.cs to cTrader Plugins directory..."
	cp src/cbot/CustomDataSourceHistDataPlugin.cs $(CTRADER_PLUGIN_DST)
	@echo "Deployment complete! Please rebuild the bot and plugin in cTrader Automate."

docs:
	uv run mkdocs serve -a 127.0.0.1:8001

docs-build:
	uv run mkdocs build

docs-contract:
	uv run python scripts/build_docs_catalog.py
	uv run python scripts/build_oco_execution_drift_report.py
	uv run python scripts/build_oco_threshold_sensitivity_report.py
	uv run python scripts/build_ftmo_allocator_monitoring_report.py
	uv run python scripts/reconcile_ftmo_reservations.py
	uv run python scripts/validate_oco_rule_universe_registry.py
	uv run python scripts/remediate_oco_monitoring_alerts.py
	uv run python scripts/build_oco_governance_explainability_report.py
	uv run python scripts/build_operator_action_report.py
	uv run python scripts/build_oco_strategy_bible.py --manifest configs/research/docs/oco_bible_manifest.yaml --strict false
	uv run python scripts/build_oco_system_reference_docs.py
	uv run python scripts/build_symbol_onboarding_playbook.py
	uv run python scripts/check_oco_docs_stage_integrity.py
	uv run python scripts/validate_oco_docs_contract.py

docs-contract-ci:
	uv run python scripts/build_docs_catalog.py
	uv run python scripts/build_ftmo_allocator_monitoring_report.py
	uv run python scripts/reconcile_ftmo_reservations.py
	uv run python scripts/validate_oco_rule_universe_registry.py
	uv run python scripts/remediate_oco_monitoring_alerts.py
	uv run python scripts/build_oco_governance_explainability_report.py
	uv run python scripts/build_operator_action_report.py
	uv run python scripts/build_oco_strategy_bible.py --manifest configs/research/docs/oco_bible_manifest.yaml --strict false
	uv run python scripts/build_oco_system_reference_docs.py
	uv run python scripts/check_oco_docs_stage_integrity.py
	uv run python scripts/validate_oco_docs_contract.py

audit-all:
	@echo "\n--- Running Core Audits ---"
	uv run python scripts/audit_oco_pipeline_logical_issues.py
	uv run python scripts/audit_oco_leakage_label_integrity.py
	uv run python scripts/audit_oco_execution_risk_prelive.py

freeze-oco:
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "error: freeze-oco requires a clean git worktree before running."; \
		echo "hint: commit/stash current changes, then rerun make freeze-oco"; \
		exit 1; \
	fi
	@echo "\n--- Verifying API Parity ---"
	@for sym in $(REBUILD_SYMBOLS); do \
		echo "Parity check: $$sym"; \
		JSON=$$(ls models/oco/$${sym}_model_*.json | sort | tail -n 1); \
		if [ -z "$$JSON" ]; then echo "Error: No model JSON found for $$sym"; exit 1; fi; \
		uv run python scripts/validate_api_parity.py --symbol $$sym \
			--predictions data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/$${sym}_oco_monthly_predictions.parquet \
			--threshold-json $$JSON || exit 1; \
		done
	@echo "\n--- Refreezing Governance Locks ---"
	uv run python scripts/freeze_oco_live_governance.py --symbols $(shell echo $(REBUILD_SYMBOLS) | sed 's/ /,/g')
	@echo "\n--- Running Core Audits ---"
	$(MAKE) audit-all
	$(MAKE) docs-contract-ci
	@echo "\n✅ Successfully audited and frozen all locks."

freeze-oco-history:
	uv run python scripts/freeze_oco_historical_governance.py --symbols $(shell echo $(REBUILD_SYMBOLS) | sed 's/ /,/g')
	$(MAKE) validate-oco-history
	@echo "\n✅ Historical month-scoped locks generated."

validate-oco-history:
	uv run python scripts/validate_oco_historical_governance.py \
		--history-dir configs/research/governance/oco_history \
		--symbols $(shell echo $(REBUILD_SYMBOLS) | sed 's/ /,/g')

reconcile-historical-predictions:
	uv run python scripts/reconcile_historical_prediction_artifacts.py \
		--history-dir $(or $(HISTORY_DIR),configs/research/governance/oco_history) \
		--tick-velocity-dir $(or $(TICK_VELOCITY_DIR),data/analysis/tick_velocity) \
		--symbols $(or $(SYMBOLS),) \
		--months $(or $(MONTHS),) \
		--write-lock $(or $(WRITE_LOCK),true) \
		$(if $(SUMMARY_CSV),--summary-csv $(SUMMARY_CSV),)

summarize-runtime-db-run:
	@test -n "$(SYMBOL)" || (echo "error: SYMBOL is required, e.g. make summarize-runtime-db-run SYMBOL=EURUSD START_TS=2025-07-01T00:00:00Z END_TS=2025-08-01T00:00:00Z" && exit 1)
	uv run python scripts/summarize_runtime_db_run.py \
		--runtime-db $(or $(RUNTIME_DB),data/db/behemoth_runtime.db) \
		--symbol $(SYMBOL) \
		--start-ts $(START_TS) \
		--end-ts $(END_TS) \
		--out-csv $(or $(OUT_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_runtime_db_run_summary.csv) \
		--report-out $(or $(REPORT_OUT),docs/analysis/$(SYMBOL)_runtime_db_run_summary.md)

reconcile-ctrader-run:
	@test -n "$(SYMBOL)" || (echo "error: SYMBOL is required" && exit 1)
	@test -n "$(PRED_PATH)" || (echo "error: PRED_PATH is required, e.g. data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet" && exit 1)
	uv run python scripts/reconcile_ctrader_vs_research.py \
		--symbol $(SYMBOL) \
		--runtime-db $(or $(RUNTIME_DB),data/db/behemoth_runtime.db) \
		--predictions-parquet $(PRED_PATH) \
		$(if $(HISTORY_DIR),--history-dir $(HISTORY_DIR),) \
		$(if $(TICK_ROOT),--tick-root $(TICK_ROOT),) \
		--start-ts $(START_TS) \
		--end-ts $(END_TS) \
		--strict-window $(or $(STRICT_WINDOW),true) \
		--timestamp-tolerance-sec $(or $(TOL_SEC),2.0) \
		--out-checks-csv $(or $(OUT_CHECKS_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_ctrader_vs_research_checks.csv) \
		--out-mismatches-csv $(or $(OUT_MISMATCHES_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_ctrader_vs_research_mismatches.csv) \
		--report-out $(or $(REPORT_OUT),docs/analysis/$(SYMBOL)_ctrader_vs_research_reconciliation.md)

export-ctrader-custom-data:
	@test -n "$(SYMBOL)" || (echo "error: SYMBOL is required, e.g. make export-ctrader-custom-data SYMBOL=EURUSD START_TS=2025-07-07T00:00:00Z END_TS=2025-07-09T00:00:00Z OUT_DIR=data/analysis/backtest_reconcile/EURUSD_histdata_custom_20250707_20250709" && exit 1)
	@test -n "$(START_TS)" || (echo "error: START_TS is required" && exit 1)
	@test -n "$(END_TS)" || (echo "error: END_TS is required" && exit 1)
	@test -n "$(OUT_DIR)" || (echo "error: OUT_DIR is required" && exit 1)
	uv run python scripts/export_ctrader_custom_data.py \
		--symbol $(SYMBOL) \
		--source $(or $(SOURCE),histdata) \
		--tick-root $(if $(filter dukascopy,$(or $(SOURCE),histdata)),$(or $(DUKASCOPY_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks),$(or $(TICK_ROOT),/Users/danielfisher/Desktop/tick)) \
		--start-ts $(START_TS) \
		--end-ts $(END_TS) \
		--out-dir $(OUT_DIR) \
		--overwrite $(or $(OVERWRITE),false) \
		$(if $(SUMMARY_CSV),--summary-csv $(SUMMARY_CSV),)

ctrader-debug-up:
	@test -n "$(SYMBOL)" || (echo "error: SYMBOL is required" && exit 1)
	@test -n "$(START_TS)" || (echo "error: START_TS is required" && exit 1)
	@test -n "$(END_TS)" || (echo "error: END_TS is required" && exit 1)
	uv run python scripts/manage_ctrader_debug_session.py up \
		--source $(or $(SOURCE),histdata) \
		--symbol $(SYMBOL) \
		--start-ts $(START_TS) \
		--end-ts $(END_TS) \
		$(if $(RUN_ID),--run-id $(RUN_ID),) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/tick) \
		--dukascopy-root $(or $(DUKASCOPY_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks) \
		--host $(or $(HOST),127.0.0.1) \
		--port $(or $(PORT),8000) \
		--start-api $(or $(START_API),true) \
		--replace-active $(or $(REPLACE_ACTIVE),true) \
		--reset-db $(or $(RESET_DB),true) \
		--overwrite-package $(or $(OVERWRITE_PACKAGE),true) \
		--record-raw-ticks $(or $(RECORD_RAW_TICKS),true) \
		--start-timeout-sec $(or $(START_TIMEOUT_SEC),20.0) \
		--models-dir $(or $(MODELS_DIR),models/oco) \
		--history-dir $(or $(HISTORY_DIR),configs/research/governance/oco_history) \
		--missing-month-policy $(or $(MISSING_MONTH_POLICY),error) \
		--historical-preflight-mode $(or $(HISTORICAL_PREFLIGHT_MODE),warn) \
		--historical-prediction-universe-mode $(or $(HISTORICAL_PREDICTION_UNIVERSE_MODE),tolerant) \
		--ftmo-rules-path $(or $(FTMO_RULES_PATH),configs/research/governance/ftmo/ftmo_rules.yaml) \
		--ftmo-profile-id $(or $(FTMO_PROFILE_ID),ftmo_10k_challenge_2step) \
		--ftmo-phase-mode $(or $(FTMO_PHASE_MODE),full_lifecycle) \
		--ftmo-economics-mode $(or $(FTMO_ECONOMICS_MODE),repo_overlay) \
		--ftmo-trade-cost-gate-mode $(or $(FTMO_TRADE_COST_GATE_MODE),warn) \
		--comparison-anchor-ts $(or $(COMPARISON_ANCHOR_TS),$(START_TS)) \
		--ticks-before-anchor $(or $(WARMUP_TICKS),30000) \
		--ticks-after-anchor $(or $(COMPARISON_TICKS),30000)

ctrader-debug-down:
	uv run python scripts/manage_ctrader_debug_session.py down \
		$(if $(RUN_ID),--run-id $(RUN_ID),) \
		--clear-active $(or $(CLEAR_ACTIVE),true)

ctrader-debug-status:
	uv run python scripts/manage_ctrader_debug_session.py status \
		$(if $(RUN_ID),--run-id $(RUN_ID),)

cbot-surrogate:
	@test -n "$(SYMBOL)" || (echo "error: SYMBOL is required" && exit 1)
	@test -n "$(START_TS)" || (echo "error: START_TS is required" && exit 1)
	@test -n "$(END_TS)" || (echo "error: END_TS is required" && exit 1)
	uv run python scripts/replay_histdata_cbot_surrogate.py \
		--symbol $(SYMBOL) \
		--start-ts $(START_TS) \
		--end-ts $(END_TS) \
		$(if $(RUN_ID),--run-id $(RUN_ID),) \
		--source $(or $(SOURCE),histdata) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/tick) \
		--dukascopy-root $(or $(DUKASCOPY_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks) \
		--warmup-ticks $(or $(WARMUP_TICKS),30000) \
		--lookback-days $(or $(LOOKBACK_DAYS),31) \
		--models-dir $(or $(MODELS_DIR),models/oco) \
		--history-dir $(or $(HISTORY_DIR),configs/research/governance/oco_history) \
		--missing-month-policy $(or $(MISSING_MONTH_POLICY),error) \
		--historical-preflight-mode $(or $(HISTORICAL_PREFLIGHT_MODE),warn) \
		--historical-prediction-universe-mode $(or $(HISTORICAL_PREDICTION_UNIVERSE_MODE),tolerant) \
		--ftmo-enabled-override $(or $(FTMO_ENABLED_OVERRIDE),true) \
		--ftmo-rules-path $(or $(FTMO_RULES_PATH),configs/research/governance/ftmo/ftmo_rules.yaml) \
		--ftmo-profile-id $(or $(FTMO_PROFILE_ID),ftmo_10k_challenge_2step) \
		--ftmo-phase-mode $(or $(FTMO_PHASE_MODE),full_lifecycle) \
		--ftmo-economics-mode $(or $(FTMO_ECONOMICS_MODE),repo_overlay) \
		--ftmo-trade-cost-gate-mode $(or $(FTMO_TRADE_COST_GATE_MODE),warn) \
		--requested-lot-size $(or $(REQUESTED_LOT_SIZE),0.05) \
		--enable-tick-batch $(or $(ENABLE_TICK_BATCH),true) \
		--tick-batch-size $(or $(TICK_BATCH_SIZE),20) \
		--selected-time-tolerance-sec $(or $(SELECTED_TIME_TOLERANCE_SEC),30.0) \
		--selected-parity-mode $(or $(SELECTED_PARITY_MODE),event_aligned) \
		--enable-sequence-fallback $(or $(ENABLE_SEQUENCE_FALLBACK),true) \
		--sequence-fallback-max-gap-sec $(or $(SEQUENCE_FALLBACK_MAX_GAP_SEC),21600.0) \
		--reset-runtime-db $(or $(RESET_RUNTIME_DB),true) \
		--record-raw-ticks $(or $(RECORD_RAW_TICKS),true) \
		--time-tolerance-sec $(or $(TIME_TOLERANCE_SEC),30.0) \
		--price-tolerance-pips $(or $(PRICE_TOLERANCE_PIPS),0.1) \
		$(if $(REPO_PREDICTIONS_PARQUET),--repo-predictions-parquet $(REPO_PREDICTIONS_PARQUET),) \
		$(if $(REPO_STOPLIMIT_DETAIL_CSV),--repo-stoplimit-detail-csv $(REPO_STOPLIMIT_DETAIL_CSV),) \
		$(if $(REDUCED_CORE_STATE_SCHEDULE_CSV),--reduced-core-state-schedule-csv $(REDUCED_CORE_STATE_SCHEDULE_CSV),)

ftmo-eval:
	@test -n "$(SESSION_JSON)" || (echo "error: SESSION_JSON is required" && exit 1)
	uv run python scripts/evaluate_ftmo_challenge_run.py \
		--session-json $(SESSION_JSON) \
		$(if $(OUT_DIR),--out-dir $(OUT_DIR),) \
		--phase-mode $(or $(FTMO_PHASE_MODE),full_lifecycle) \
		--economics-mode $(or $(FTMO_ECONOMICS_MODE),repo_overlay) \
		--incomplete-verdict $(or $(INCOMPLETE_VERDICT),in_progress)

ctrader-ab-parity-report:
	@test -n "$(SYMBOL)" || (echo "error: SYMBOL is required" && exit 1)
	@test -n "$(RUNTIME_DB_A)" || (echo "error: RUNTIME_DB_A is required" && exit 1)
	@test -n "$(RUNTIME_DB_B)" || (echo "error: RUNTIME_DB_B is required" && exit 1)
	@test -n "$(PRED_PATH)" || (echo "error: PRED_PATH is required" && exit 1)
	@test -n "$(START_TS)" || (echo "error: START_TS is required" && exit 1)
	@test -n "$(END_TS)" || (echo "error: END_TS is required" && exit 1)
	uv run python scripts/build_ctrader_ab_parity_report.py \
		--symbol $(SYMBOL) \
		--runtime-db-a $(RUNTIME_DB_A) \
		--runtime-db-b $(RUNTIME_DB_B) \
		--predictions-parquet $(PRED_PATH) \
		$(if $(TICK_ROOT),--tick-root $(TICK_ROOT),) \
		$(if $(HISTORY_DIR),--history-dir $(HISTORY_DIR),) \
		--start-ts $(START_TS) \
		--end-ts $(END_TS) \
		--strict-window $(or $(STRICT_WINDOW),true) \
		--timestamp-tolerance-sec $(or $(TOL_SEC),2.0) \
		--out-summary-csv $(or $(OUT_SUMMARY_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_ctrader_ab_parity_summary.csv) \
		--out-checks-csv $(or $(OUT_CHECKS_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_ctrader_ab_parity_checks.csv) \
		--report-out $(or $(REPORT_OUT),docs/analysis/$(SYMBOL)_ctrader_ab_parity_report.md)

histdata-ctrader-parity:
	@test -n "$(SYMBOL)" || (echo "error: SYMBOL is required" && exit 1)
	@test -n "$(RUNTIME_DB)" || (echo "error: RUNTIME_DB is required" && exit 1)
	@test -n "$(CTRADER_EVENTS_JSON)" || (echo "error: CTRADER_EVENTS_JSON is required" && exit 1)
	@test -n "$(REPO_DETAIL_CSV)" || (echo "error: REPO_DETAIL_CSV is required" && exit 1)
	@test -n "$(REDUCED_STATE_SCHEDULE_CSV)" || (echo "error: REDUCED_STATE_SCHEDULE_CSV is required" && exit 1)
	@test -n "$(START_TS)" || (echo "error: START_TS is required" && exit 1)
	@test -n "$(END_TS)" || (echo "error: END_TS is required" && exit 1)
	uv run python scripts/validate_histdata_ctrader_execution_parity.py \
		--symbol $(SYMBOL) \
		--runtime-db $(RUNTIME_DB) \
		--ctrader-events-json $(CTRADER_EVENTS_JSON) \
		--repo-stoplimit-detail-csv $(REPO_DETAIL_CSV) \
		--reduced-core-state-schedule-csv $(REDUCED_STATE_SCHEDULE_CSV) \
		--require-reduced-core-filter true \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/tick) \
		--start-ts $(START_TS) \
		--end-ts $(END_TS) \
		--time-tolerance-sec $(or $(TIME_TOL_SEC),1.0) \
		--price-tolerance-pips $(or $(PRICE_TOL_PIPS),0.1) \
		--out-summary-csv $(or $(OUT_SUMMARY_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_histdata_ctrader_execution_parity_summary.csv) \
		--out-checks-csv $(or $(OUT_CHECKS_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_histdata_ctrader_execution_parity_checks.csv) \
		--out-mismatches-csv $(or $(OUT_MISMATCHES_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_histdata_ctrader_execution_parity_mismatches.csv) \
		--report-out $(or $(REPORT_OUT),docs/analysis/$(SYMBOL)_histdata_ctrader_execution_parity_report.md)

histdata-testclient-parity:
	@test -n "$(SYMBOL)" || (echo "error: SYMBOL is required" && exit 1)
	@test -n "$(RUNTIME_DB)" || (echo "error: RUNTIME_DB is required" && exit 1)
	@test -n "$(EVENTS_JSON)" || (echo "error: EVENTS_JSON is required" && exit 1)
	@test -n "$(REPO_PREDICTIONS_PARQUET)" || (echo "error: REPO_PREDICTIONS_PARQUET is required" && exit 1)
	@test -n "$(REPO_DETAIL_CSV)" || (echo "error: REPO_DETAIL_CSV is required" && exit 1)
	@test -n "$(REDUCED_STATE_SCHEDULE_CSV)" || (echo "error: REDUCED_STATE_SCHEDULE_CSV is required" && exit 1)
	@test -n "$(START_TS)" || (echo "error: START_TS is required" && exit 1)
	@test -n "$(END_TS)" || (echo "error: END_TS is required" && exit 1)
	uv run python scripts/replay_histdata_cbot_testclient.py \
		--symbol $(SYMBOL) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/tick) \
		--runtime-db $(RUNTIME_DB) \
		--events-json $(EVENTS_JSON) \
		--repo-predictions-parquet $(REPO_PREDICTIONS_PARQUET) \
		--repo-stoplimit-detail-csv $(REPO_DETAIL_CSV) \
		--reduced-core-state-schedule-csv $(REDUCED_STATE_SCHEDULE_CSV) \
		--start-ts $(START_TS) \
		--end-ts $(END_TS) \
		--warmup-ticks $(or $(WARMUP_TICKS),30000) \
		--lookback-days $(or $(LOOKBACK_DAYS),31) \
		--warmup-source $(or $(WARMUP_SOURCE),history_tail) \
		--phase-bar-ticks $(or $(PHASE_BAR_TICKS),100) \
		$(if $(MODEL_MONTH),--model-month $(MODEL_MONTH),) \
		--models-dir $(or $(MODELS_DIR),models/oco) \
		--history-dir $(or $(HISTORY_DIR),configs/research/governance/oco_history) \
		--missing-month-policy $(or $(MISSING_MONTH_POLICY),error) \
		--ftmo-enabled-override $(or $(FTMO_ENABLED_OVERRIDE),false) \
		--requested-lot-size $(or $(LOT_SIZE),0.05) \
		--enable-tick-batch $(or $(ENABLE_TICK_BATCH),true) \
		--tick-batch-size $(or $(TICK_BATCH_SIZE),20) \
		--selected-time-tolerance-sec $(or $(SELECTED_TIME_TOL_SEC),1.0) \
		--enable-sequence-fallback $(or $(ENABLE_SEQUENCE_FALLBACK),false) \
		--sequence-fallback-max-gap-sec $(or $(SEQUENCE_FALLBACK_MAX_GAP_SEC),21600) \
		--reset-runtime-db $(or $(RESET_RUNTIME_DB),true) \
		--record-raw-ticks $(or $(RECORD_RAW_TICKS),true) \
		--time-tolerance-sec $(or $(TIME_TOL_SEC),1.0) \
		--price-tolerance-pips $(or $(PRICE_TOL_PIPS),0.1) \
		--out-summary-csv $(or $(OUT_SUMMARY_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_histdata_testclient_execution_parity_summary.csv) \
		--out-checks-csv $(or $(OUT_CHECKS_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_histdata_testclient_execution_parity_checks.csv) \
		--out-mismatches-csv $(or $(OUT_MISMATCHES_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_histdata_testclient_execution_parity_mismatches.csv) \
		--report-out $(or $(REPORT_OUT),docs/analysis/$(SYMBOL)_histdata_testclient_execution_parity_report.md) \
		--local-summary-csv $(or $(LOCAL_SUMMARY_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_histdata_testclient_replay_summary.csv) \
		--local-selected-mismatches-csv $(or $(LOCAL_SELECTED_MISMATCHES_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_histdata_testclient_selected_mismatches.csv) \
		--stage12-summary-csv $(or $(STAGE12_SUMMARY_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_stage12_api_parity_summary.csv) \
		--stage12-checks-csv $(or $(STAGE12_CHECKS_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_stage12_api_parity_checks.csv) \
		--stage12-mismatches-csv $(or $(STAGE12_MISMATCHES_CSV),data/analysis/backtest_reconcile/$(SYMBOL)_stage12_api_parity_mismatches.csv) \
		--stage12-report-out $(or $(STAGE12_REPORT_OUT),docs/analysis/$(SYMBOL)_stage12_api_parity_report.md) \
		--fail-on-gate $(or $(FAIL_ON_GATE),true) \
		--require-selected-parity $(or $(REQUIRE_SELECTED_PARITY),true)

stage12-api-parity: histdata-testclient-parity

offset-robustness-study:
	uv run python scripts/run_offset_tickbar_robustness.py \
		--symbols $(if $(SYMBOLS),$(SYMBOLS),$(OFFSET_ROBUSTNESS_SYMBOLS_DEFAULT)) \
		--offsets $(if $(OFFSETS),$(OFFSETS),$(OFFSET_ROBUSTNESS_OFFSETS_DEFAULT)) \
		--mode $(or $(MODE),adaptive) \
		--coarse-offsets $(if $(COARSE_OFFSETS),$(COARSE_OFFSETS),$(OFFSET_ROBUSTNESS_COARSE_DEFAULT)) \
		--refine-radius $(or $(REFINE_RADIUS),2) \
		--max-refine-centers-per-symbol $(or $(MAX_REFINE_CENTERS_PER_SYMBOL),2) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/tick) \
		--offset-bar-dir $(or $(OFFSET_BAR_DIR),data/global_tickbars_offset) \
		--out-dir $(or $(OUT_DIR),data/analysis/tick_opportunity_mining/offset_robustness) \
		--retention-mode $(or $(RETENTION_MODE),compact) \
		--retain-flagged-offset-runs $(or $(RETAIN_FLAGGED_OFFSET_RUNS),true) \
		--api-confirm-offsets $(if $(API_CONFIRM_OFFSETS),$(API_CONFIRM_OFFSETS),$(OFFSET_ROBUSTNESS_API_CONFIRM_DEFAULT)) \
		--warmup-bars-grid $(if $(WARMUP_BARS_GRID),$(WARMUP_BARS_GRID),$(OFFSET_ROBUSTNESS_WARMUP_DEFAULT)) \
		--stage12-start-ts $(or $(START_TS),2025-07-07T00:00:00Z) \
		--stage12-end-ts $(or $(END_TS),2025-07-09T00:00:00Z) \
		$(if $(OVERWRITE_OFFSET_BARS),--overwrite-offset-bars,) \
		$(if $(SKIP_API_CONFIRMATION),--skip-api-confirmation,) \
		$(if $(SKIP_WARMUP_SENSITIVITY),--skip-warmup-sensitivity,) \
		$(if $(FAIL_FAST),--fail-fast,)

offset-frozen-screen:
	uv run python scripts/run_offset_tickbar_frozen_screen.py \
		--symbols $(if $(SYMBOLS),$(SYMBOLS),$(OFFSET_ROBUSTNESS_SYMBOLS_DEFAULT)) \
		--offsets $(if $(OFFSETS),$(OFFSETS),$(OFFSET_ROBUSTNESS_COARSE_DEFAULT)) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/tick) \
		--offset-bar-dir $(or $(OFFSET_BAR_DIR),data/global_tickbars_offset) \
		--frozen-root $(or $(FROZEN_ROOT),data/analysis/tick_opportunity_mining/frozen_models) \
		--out-dir $(or $(OUT_DIR),data/analysis/tick_opportunity_mining/offset_robustness_frozen) \
		--retention-mode $(or $(RETENTION_MODE),compact) \
		$(if $(filter 1 true TRUE yes YES,$(CLEANUP_COMPLETED_ARTIFACTS)),--cleanup-completed-artifacts,) \
		$(if $(FAIL_FAST),--fail-fast,)

docs-clean:
	rm -rf site

precommit-install:
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

precommit-run:
	uv run pre-commit run --all-files

lint:
	uv run ruff check scripts tests

format:
	uv run ruff format scripts tests

check-legacy-drift:
	uv run python scripts/check_legacy_drift.py

help:
	@printf "$(COLOR_HEADER)Targets:$(COLOR_RESET)\n"
	@printf "\n$(COLOR_SECTION)== Quality ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "test" "Run pytest"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "quality" "Run all quality checks (ty, lint, vulture, smellcheck, radon, xenon)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "ty" "Run ty type checker"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "vulture" "Run dead code detection"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "smellcheck" "Run code smell detection"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "radon" "Run complexity analysis"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "xenon" "Run complexity enforcement"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "lint" "Run ruff lint"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "format" "Run ruff format"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "check-legacy-drift" "Check repo for legacy/forbidden code drift"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "precommit-install" "Install pre-commit hooks"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "precommit-run" "Run pre-commit on all files"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "deploy-cbot" "Copy the Behemoth cBot source into the cTrader robot source tree"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "deploy-ctrader" "Copy both the Behemoth cBot and HistData plugin into the cTrader source tree"
	@printf "\n$(COLOR_SECTION)== Pipeline ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "retrain-all" "Re-run ML pipeline + docs for all symbols (skip data download)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "rebuild-all" "Full rebuild: data + ML + docs for all symbols (MONTHS=... required)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "freeze-oco-history" "Freeze month-scoped historical governance locks for replay/backtests"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "validate-oco-history" "Validate historical lock integrity and index coverage"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "reconcile-historical-predictions" "Rebuild frozen month-local historical predictions from locked model artifacts"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "offset-robustness-study" "Run the offset tick-bar robustness study across selected symbols/offsets"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "summarize-runtime-db-run" "Summarize runtime DB rows for one symbol/window"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "reconcile-ctrader-run" "Reconcile cTrader runtime signals against research predictions"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "export-ctrader-custom-data" "Export HistData or Dukascopy parquet ticks into a cTrader custom-data package"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "ctrader-debug-up" "One-command HistData/Dukascopy debug session: export package + isolated DuckDB + FTMO-enabled API"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "ctrader-debug-down" "Stop the active cTrader debug session and clear the active package pointer"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "ctrader-debug-status" "Show the active cTrader debug session, DB path, package path, and API state"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "ctrader-ab-parity-report" "Compare baseline-vs-custom cTrader runs and build A/B parity report"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "histdata-ctrader-parity" "Validate HistData execution parity from cTrader runtime DB + events"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "histdata-testclient-parity" "Replay HistData via TestClient (no cTrader) and run strict parity gate"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "cbot-surrogate" "Replay HistData or Dukascopy through the API/runtime stack with FTMO rules enabled"
	@printf "\n$(COLOR_SECTION)== Docs ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs" "Serve docs locally"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-build" "Build docs"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-contract" "Run docs contracts and OCO docs governance checks"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-contract-ci" "Run CI-safe docs contracts without heavy recomputation"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-clean" "Remove built site/"

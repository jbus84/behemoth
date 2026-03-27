.DEFAULT_GOAL := help
COLOR_RESET := \033[0m
COLOR_HEADER := \033[1;36m
COLOR_SECTION := \033[1;35m
COLOR_TARGET := \033[0;32m
COLOR_DOC := \033[0;34m
COLOR_DESC := \033[2m

REPO_ROOT_FROM_GIT := $(abspath $(shell git rev-parse --git-common-dir 2>/dev/null)/..)

ifneq ("$(wildcard .env)","")
include .env
else ifneq ("$(wildcard $(REPO_ROOT_FROM_GIT)/.env)","")
include $(REPO_ROOT_FROM_GIT)/.env
endif

# Active symbol list — single source of truth for multi-symbol targets
REBUILD_SYMBOLS := EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD
# Default comma-separated symbol list for targets that accept --symbols (e.g. jforex-outcome-parity)
SYMBOLS ?= EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD
CTRADER_ROBOT_DST := ~/cAlgo/Sources/Robots/BehemothTradeManager/BehemothTradeManager/BehemothTradeManager.cs
CTRADER_PLUGIN_DST := ~/cAlgo/Sources/Plugins/CustomDataSourceHistDataPlugin/CustomDataSourceHistDataPlugin/CustomDataSourceHistDataPlugin.cs

.PHONY: test test-java docs docs-build docs-contract docs-contract-ci docs-clean precommit-install precommit-run lint format help onboard-symbol check-legacy-drift deploy-cbot deploy-ctrader provision observability-up observability-down retrain-all rebuild-all quality ty vulture smellcheck radon xenon audit-all freeze-oco freeze-oco-history validate-oco-history reconcile-historical-predictions summarize-runtime-db-run reconcile-ctrader-run export-ctrader-custom-data ctrader-debug-up ctrader-debug-down ctrader-debug-status ctrader-ab-parity-report ctrader-parity testclient-parity dukascopy-testclient-parity local-jforex-parity local-jforex-parity-matrix local-jforex-parity-ordinal local-jforex-parity-spotlight jforex-dukascopy-matrix jforex-outcome-parity local-jforex-cert histdata-ctrader-parity histdata-testclient-parity stage12-api-parity stage13-dukascopy-cert stage14-jforex-cert full-stage14-cert dukascopy-source-audit offset-robustness-study offset-frozen-screen account-risk-monitoring-report reconcile-account-risk-reservations jforex-live demo-cert-monitor freeze-oco-dukascopy-candidate monthly-build monthly-recert promote-live

OFFSET_ROBUSTNESS_SYMBOLS_DEFAULT := EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD
OFFSET_ROBUSTNESS_OFFSETS_DEFAULT := 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99
OFFSET_ROBUSTNESS_COARSE_DEFAULT := 0,10,20,30,40,50,60,70,80,90
OFFSET_ROBUSTNESS_API_CONFIRM_DEFAULT := 0,25,50,75
OFFSET_ROBUSTNESS_WARMUP_DEFAULT := 73,145,217,289,400

provision:
	@echo "Provisioning Alertmanager configuration..."
	uv run python scripts/provision_observability.py

observability-up:
	docker compose up -d prometheus alertmanager grafana

observability-down:
	docker compose down

test:
	uv run pytest -q

test-java:
	gradle :jforex-adapter:test

local-jforex-parity:
	BEHEMOTH_LOCAL_JFOREX_INSTRUMENTS=$(or $(SYMBOL),GBPUSD) \
	BEHEMOTH_LOCAL_JFOREX_START_UTC=$(or $(START_TS),2025-07-07T00:00:00Z) \
	BEHEMOTH_LOCAL_JFOREX_END_UTC=$(or $(END_TS),2025-07-09T00:00:00Z) \
	BEHEMOTH_LOCAL_JFOREX_TICK_ROOT=$(or $(TICK_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks) \
	BEHEMOTH_LOCAL_JFOREX_REPORT_DIR=$(or $(REPORT_DIR),data/analysis/backtest_reconcile) \
	BEHEMOTH_LOCAL_JFOREX_RUN_ID=$(or $(RUN_ID),local_jforex_surrogate) \
	BEHEMOTH_LOCAL_JFOREX_RISK_ENABLED=$(or $(RISK_ENABLED),false) \
	BEHEMOTH_LOCAL_JFOREX_REQUESTED_VOLUME_UNITS=$(or $(REQUESTED_VOLUME_UNITS),10000) \
	BEHEMOTH_LOCAL_JFOREX_TICK_BATCH_SIZE=$(or $(TICK_BATCH_SIZE),256) \
	BEHEMOTH_LOCAL_JFOREX_ORDER_TTL_SECONDS=$(or $(ORDER_TTL_SECONDS),900) \
	BEHEMOTH_LOCAL_JFOREX_API_TIMEOUT_SECONDS=$(or $(API_TIMEOUT_SECONDS),60) \
	BEHEMOTH_LOCAL_JFOREX_METRICS_ENABLED=$(or $(METRICS_ENABLED),true) \
	BEHEMOTH_LOCAL_JFOREX_METRICS_HOST=$(or $(METRICS_HOST),127.0.0.1) \
	BEHEMOTH_LOCAL_JFOREX_METRICS_PORT=$(or $(METRICS_PORT),9465) \
	BEHEMOTH_LOCAL_JFOREX_WARMUP_TICKS=$(or $(WARMUP_TICKS),30000) \
	BEHEMOTH_LOCAL_JFOREX_LOOKBACK_DAYS=$(or $(LOOKBACK_DAYS),31) \
	BEHEMOTH_LOCAL_JFOREX_PHASE_BAR_TICKS=$(or $(PHASE_BAR_TICKS),100) \
	BEHEMOTH_LOCAL_JFOREX_STARTING_BALANCE=$(or $(STARTING_BALANCE),100000) \
	BEHEMOTH_API_BASE_URI=$(or $(API_BASE_URI),http://127.0.0.1:8000) \
	mise exec -- gradle :jforex-adapter:runLocalJForexTester

local-jforex-parity-matrix:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_local_jforex_surrogate_matrix.py \
		$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
		--start-ts $(or $(START_TS),2025-07-07T00:00:00Z) \
		--end-ts $(or $(END_TS),2025-07-09T00:00:00Z) \
		--model-month $(or $(MODEL_MONTH),2025-07) \
		--models-dir $(or $(MODELS_DIR),models/oco_dukascopy_candidate) \
		--history-dir $(or $(HISTORY_DIR),configs/research/governance/oco_history_dukascopy_candidate) \
		--predictions-dir $(or $(PREDICTIONS_DIR),data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2025_m3to1_oco_fullcap) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile) \
		--api-port $(or $(API_PORT),8000) \
		--requested-volume-units $(or $(REQUESTED_VOLUME_UNITS),10000) \
		--tick-batch-size $(or $(TICK_BATCH_SIZE),200) \
		--order-ttl-seconds $(or $(ORDER_TTL_SECONDS),900) \
		--api-timeout-seconds $(or $(API_TIMEOUT_SECONDS),60) \
		--metrics-port-base $(or $(METRICS_PORT_BASE),9465) \
		--warmup-ticks $(or $(WARMUP_TICKS),30000) \
		--lookback-days $(or $(LOOKBACK_DAYS),31) \
		--phase-bar-ticks $(or $(PHASE_BAR_TICKS),100) \
		--starting-balance $(or $(STARTING_BALANCE),100000)

local-jforex-parity-ordinal:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_local_jforex_surrogate_matrix.py \
		$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
		--start-ts $(or $(START_TS),2025-07-07T00:00:00Z) \
		--end-ts $(or $(END_TS),2025-07-09T00:00:00Z) \
		--model-month $(or $(MODEL_MONTH),2025-07) \
		--models-dir $(or $(MODELS_DIR),models/oco_dukascopy_candidate) \
		--history-dir $(or $(HISTORY_DIR),configs/research/governance/oco_history_dukascopy_candidate) \
		--predictions-dir $(or $(PREDICTIONS_DIR),data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2025_m3to1_oco_fullcap) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile) \
		--api-port $(or $(API_PORT),8000) \
		--requested-volume-units $(or $(REQUESTED_VOLUME_UNITS),10000) \
		--tick-batch-size $(or $(TICK_BATCH_SIZE),200) \
		--order-ttl-seconds $(or $(ORDER_TTL_SECONDS),900) \
		--api-timeout-seconds $(or $(API_TIMEOUT_SECONDS),60) \
		--metrics-port-base $(or $(METRICS_PORT_BASE),9465) \
		--warmup-ticks $(or $(WARMUP_TICKS),30000) \
		--lookback-days $(or $(LOOKBACK_DAYS),31) \
		--phase-bar-ticks $(or $(PHASE_BAR_TICKS),100) \
		--starting-balance $(or $(STARTING_BALANCE),100000) \
		--universe-mode ordinal \
		--ordinal-tolerance $(or $(ORDINAL_TOLERANCE),1)

local-jforex-parity-spotlight:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/extract_spotlight_ticks.py \
		$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
		--model-month $(or $(MODEL_MONTH),2025-07) \
		--lock-dir $(or $(LOCK_DIR),configs/research/governance/oco_history_dukascopy_candidate/$(or $(MODEL_MONTH),2025-07)) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks) \
		--output-dir $(or $(SPOTLIGHT_DIR),data/analysis/spotlight_ticks) \
		--eval-start $(or $(EVAL_START),2025-07-07T00:00:00Z) \
		--eval-end $(or $(EVAL_END),2025-07-09T00:00:00Z) \
		--pre-bars $(or $(PRE_BARS),290)
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_local_jforex_surrogate_matrix.py \
		$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
		--start-ts 2000-01-01T00:00:00Z \
		--end-ts 2030-01-01T00:00:00Z \
		--model-month $(or $(MODEL_MONTH),2025-07) \
		--models-dir $(or $(MODELS_DIR),models/oco_dukascopy_candidate) \
		--history-dir $(or $(HISTORY_DIR),configs/research/governance/oco_history_dukascopy_candidate) \
		--predictions-dir $(or $(PREDICTIONS_DIR),data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2025_m3to1_oco_fullcap) \
		--tick-root $(or $(SPOTLIGHT_DIR),data/analysis/spotlight_ticks) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile) \
		--api-port $(or $(API_PORT),8000) \
		--requested-volume-units $(or $(REQUESTED_VOLUME_UNITS),10000) \
		--tick-batch-size $(or $(TICK_BATCH_SIZE),100) \
		--order-ttl-seconds $(or $(ORDER_TTL_SECONDS),900) \
		--api-timeout-seconds $(or $(API_TIMEOUT_SECONDS),60) \
		--metrics-port-base $(or $(METRICS_PORT_BASE),9465) \
		--warmup-ticks 0 \
		--lookback-days 0 \
		--phase-bar-ticks $(or $(PHASE_BAR_TICKS),100) \
		--starting-balance $(or $(STARTING_BALANCE),100000) \
		--universe-mode $(or $(UNIVERSE_MODE),tolerant) \
		--prediction-tolerance-sec $(or $(PREDICTION_TOLERANCE_SEC),1) \
		--locked-predictions-dir $(or $(LOCKED_PREDICTIONS_DIR),configs/research/governance/oco_history_dukascopy_candidate/2025-07)
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/reconcile_jforex_outcomes.py \
		$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
		--lock-dir $(or $(LOCK_DIR),configs/research/governance/oco_history_dukascopy_candidate/2025-07) \
		--reconcile-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile) \
		--eval-start $(or $(EVAL_START),2025-07-07T00:00:00Z) \
		--eval-end $(or $(EVAL_END),2025-07-09T00:00:00Z) \
		--signal-coverage-threshold $(or $(SIGNAL_COVERAGE_THRESHOLD),1.0) \
		--out-csv $(or $(REPORT_DIR),data/analysis/backtest_reconcile)/jforex_outcome_parity_summary.csv

jforex-dukascopy-matrix:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_jforex_dukascopy_matrix.py \
		$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
		--start-ts $(or $(START_TS),2025-07-04T00:00:00Z) \
		--end-ts $(or $(END_TS),2025-07-09T00:00:00Z) \
		--model-month $(or $(MODEL_MONTH),2025-07) \
		--models-dir $(or $(MODELS_DIR),models/oco_dukascopy_candidate) \
		--history-dir $(or $(HISTORY_DIR),configs/research/governance/oco_history_dukascopy_candidate) \
		--predictions-dir $(or $(PREDICTIONS_DIR),data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2025_m3to1_oco_fullcap) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile) \
		--api-port $(or $(API_PORT),8000) \
		--requested-volume-units $(or $(REQUESTED_VOLUME_UNITS),10000) \
		--tick-batch-size $(or $(TICK_BATCH_SIZE),200) \
		--order-ttl-seconds $(or $(ORDER_TTL_SECONDS),900) \
		--api-timeout-seconds $(or $(API_TIMEOUT_SECONDS),60) \
		--metrics-port-base $(or $(METRICS_PORT_BASE),9464)

jforex-live:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_jforex_live.py \
		$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile) \
		--models-dir $(or $(MODELS_DIR),models/oco_dukascopy_candidate) \
		--history-dir $(or $(HISTORY_DIR),configs/research/governance/oco_history_dukascopy_candidate) \
		--api-port $(or $(API_PORT),8000) \
		--requested-volume-units $(or $(REQUESTED_VOLUME_UNITS),10000) \
		--tick-batch-size $(or $(TICK_BATCH_SIZE),200) \
		--order-ttl-seconds $(or $(ORDER_TTL_SECONDS),900) \
		--api-timeout-seconds $(or $(API_TIMEOUT_SECONDS),60) \
		--metrics-port $(or $(METRICS_PORT),9464)

demo-cert-monitor: observability-up
	@printf "[demo-cert] Grafana: http://127.0.0.1:3000/d/behemoth-jforex-runtime/behemoth-jforex-runtime?orgId=1\n"
	@printf "[demo-cert] Prometheus: http://127.0.0.1:9090\n"
	@printf "[demo-cert] JForex metrics: http://127.0.0.1:%s/metrics\n" "$(or $(METRICS_PORT),9464)"
	@printf "[demo-cert] Runtime readiness: %s/runtime/live_symbol_readiness.json\n" "$(or $(REPORT_DIR),data/analysis/backtest_reconcile)"
	@printf "[demo-cert] Monitoring stack: started via make observability-up\n"
	@printf "[demo-cert] Start demo runner with: make jforex-live\n"

jforex-outcome-parity:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/reconcile_jforex_outcomes.py \
		--symbols $(SYMBOLS) \
		--lock-dir $(or $(LOCK_DIR),configs/research/governance/oco_history_dukascopy_candidate/2025-07) \
		--reconcile-dir $(or $(RECONCILE_DIR),data/analysis/backtest_reconcile) \
		--eval-start $(or $(EVAL_START),2025-07-07T00:00:00Z) \
		--eval-end $(or $(EVAL_END),2025-07-09T00:00:00Z) \
		--signal-coverage-threshold $(or $(SIGNAL_COVERAGE_THRESHOLD),1.0) \
		--out-csv $(or $(OUT_CSV),data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv)

local-jforex-cert:
	uv run python scripts/validate_local_jforex_surrogate.py \
		--lock-dir $(or $(LOCK_DIR),configs/research/governance/oco) \
		--local-signal-summary-glob '$(or $(LOCAL_SIGNAL_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_local_jforex_signal_parity_summary.csv)' \
		--local-execution-summary-glob '$(or $(LOCAL_EXECUTION_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_local_jforex_execution_parity_summary.csv)' \
		--local-lifecycle-summary-glob '$(or $(LOCAL_LIFECYCLE_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_local_jforex_oco_lifecycle_summary.csv)' \
		--local-operational-summary-glob '$(or $(LOCAL_OPERATIONAL_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_local_jforex_operational_ready_summary.csv)' \
		--local-outcome-summary-glob '$(or $(LOCAL_OUTCOME_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_local_jforex_outcome_parity_summary.csv)' \
		--out-summary-csv $(or $(OUT_SUMMARY_CSV),data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv) \
		--out-checks-csv $(or $(OUT_CHECKS_CSV),data/analysis/backtest_reconcile/local_jforex_surrogate_checks.csv) \
		--report-out $(or $(REPORT_OUT),docs/analysis/local_jforex_surrogate_report.md)

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

docs:
	uv run mkdocs serve -a 127.0.0.1:8001

docs-build:
	uv run mkdocs build

docs-contract:
	uv run python scripts/build_docs_catalog.py
	uv run python scripts/build_oco_execution_drift_report.py
	uv run python scripts/build_oco_threshold_sensitivity_report.py
	uv run python scripts/build_account_risk_monitoring_report.py
	uv run python scripts/reconcile_account_risk_reservations.py
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
	uv run python scripts/build_account_risk_monitoring_report.py
	uv run python scripts/reconcile_account_risk_reservations.py
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
		SYM_LOWER=$$(echo $$sym | tr '[:upper:]' '[:lower:]'); \
		uv run python scripts/validate_api_parity.py --symbol $$sym \
			--predictions data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap_$${SYM_LOWER}/$${sym}_oco_monthly_predictions.parquet \
			--threshold-json $$JSON \
			--out-summary data/analysis/backtest_reconcile/$${sym}_stage12_api_parity_summary.csv || exit 1; \
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

freeze-oco-dukascopy-candidate:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/freeze_oco_live_governance.py \
		--symbols $(shell echo $(REBUILD_SYMBOLS) | sed 's/ /,/g') \
		--out-dir configs/research/governance/oco_dukascopy_candidate \
		--config-dir configs/research/experiments_dukascopy_candidate \
		--analysis-dir data/analysis/tick_opportunity_mining_dukascopy_candidate
	@echo "\n✅ Dukascopy-candidate governance locks frozen."

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

stage12-api-parity:

stage13-dukascopy-cert:
	uv run python scripts/validate_stage13_dukascopy_testclient.py \
		--lock-dir $(or $(LOCK_DIR),configs/research/governance/oco_history_dukascopy_candidate/2025-07) \
		--jforex-signal-summary-glob '$(or $(JFOREX_SIGNAL_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_jforex_signal_parity_summary.csv)' \
		--jforex-operational-summary-glob '$(or $(JFOREX_OPERATIONAL_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_jforex_operational_ready_summary.csv)' \
		--reconcile-dir $(or $(RECONCILE_DIR),data/analysis/backtest_reconcile) \
		--out-summary-csv $(or $(OUT_SUMMARY_CSV),data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv) \
		--out-checks-csv $(or $(OUT_CHECKS_CSV),data/analysis/backtest_reconcile/stage13_dukascopy_testclient_checks.csv) \
		--report-out $(or $(REPORT_OUT),docs/analysis/stage13_dukascopy_testclient_report.md) \
		--snapshot-out $(or $(SNAPSHOT_OUT),docs/strategy_bible/generated/stage_13_snapshot.md)

stage14-jforex-cert:
	uv run python scripts/validate_stage14_jforex_runtime_certification.py \
		--stage13-summary-glob '$(or $(STAGE13_SUMMARY_GLOB),data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv)' \
		--jforex-signal-summary-glob '$(or $(JFOREX_SIGNAL_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_jforex_signal_parity_summary.csv)' \
		--jforex-execution-summary-glob '$(or $(JFOREX_EXECUTION_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_jforex_execution_parity_summary.csv)' \
		--jforex-lifecycle-summary-glob '$(or $(JFOREX_LIFECYCLE_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_jforex_oco_lifecycle_summary.csv)' \
		--jforex-operational-summary-glob '$(or $(JFOREX_OPERATIONAL_SUMMARY_GLOB),data/analysis/backtest_reconcile/*_jforex_operational_ready_summary.csv)' \
		--jforex-outcome-summary-glob '$(or $(JFOREX_OUTCOME_SUMMARY_GLOB),data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv)' \
		--local-surrogate-summary-glob '$(or $(LOCAL_SURROGATE_SUMMARY_GLOB),data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv)' \
		--max-artifact-age-days $(or $(MAX_ARTIFACT_AGE_DAYS),35) \
		--out-summary-csv $(or $(OUT_SUMMARY_CSV),data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv) \
		--out-checks-csv $(or $(OUT_CHECKS_CSV),data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv) \
		--report-out $(or $(REPORT_OUT),docs/analysis/stage14_jforex_runtime_certification_report.md) \
		--snapshot-out $(or $(SNAPSHOT_OUT),docs/strategy_bible/generated/stage_14_snapshot.md)

full-stage14-cert: jforex-outcome-parity local-jforex-cert stage14-jforex-cert

monthly-recert:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_monthly_recert.py \
		$(if $(MODEL_MONTH),--model-month "$(MODEL_MONTH)",) \
		$(if $(START_TS),--start-ts "$(START_TS)",) \
		$(if $(END_TS),--end-ts "$(END_TS)",) \
		$(if $(EVAL_START),--eval-start "$(EVAL_START)",) \
		$(if $(EVAL_END),--eval-end "$(EVAL_END)",) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile)

monthly-build:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_monthly_build.py \
		$(if $(MODEL_MONTH),--model-month "$(MODEL_MONTH)",)

promote-live:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_promote_live.py \
		$(if $(MODEL_MONTH),--model-month "$(MODEL_MONTH)",) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile)

account-risk-monitoring-report:
	uv run python scripts/build_account_risk_monitoring_report.py

reconcile-account-risk-reservations:
	uv run python scripts/reconcile_account_risk_reservations.py

dukascopy-source-audit:
	uv run python scripts/audit_tick_source_completeness.py \
		--tick-root $(or $(DUKASCOPY_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks) \
		$(if $(SYMBOLS),--symbols $(SYMBOLS),) \
		$(if $(MONTHS),--months $(MONTHS),) \
		--registry-path $(or $(REGISTRY_PATH),configs/research/governance/oco_rule_universe_registry.yaml) \
		--history-dir $(or $(HISTORY_DIR),configs/research/governance/oco_history) \
		--out-summary-csv $(or $(OUT_SUMMARY_CSV),data/analysis/tick_opportunity_mining/dukascopy_source_completeness_summary.csv) \
		--out-missing-csv $(or $(OUT_MISSING_CSV),data/analysis/tick_opportunity_mining/dukascopy_source_completeness_missing.csv) \
		--report-out $(or $(REPORT_OUT),docs/analysis/dukascopy_source_completeness_report.md)

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
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "test-java" "Run JForex adapter unit tests via Gradle"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "check-legacy-drift" "Check repo for legacy/forbidden code drift"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "precommit-install" "Install pre-commit hooks"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "precommit-run" "Run pre-commit on all files"
	@printf "\n$(COLOR_SECTION)== Pipeline ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "retrain-all" "Re-run ML pipeline + docs for all symbols (skip data download)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "rebuild-all" "Full rebuild: data + ML + docs for all symbols (MONTHS=... required)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "freeze-oco-history" "Freeze month-scoped historical governance locks for replay/backtests"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "validate-oco-history" "Validate historical lock integrity and index coverage"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "reconcile-historical-predictions" "Rebuild frozen month-local historical predictions from locked model artifacts"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "offset-robustness-study" "Run the offset tick-bar robustness study across selected symbols/offsets"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "dukascopy-source-audit" "Audit Dukascopy symbol/month completeness against the active universe and history locks"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "summarize-runtime-db-run" "Summarize runtime DB rows for one symbol/window"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "local-jforex-parity" "Run the local parquet-driven JForex surrogate against the shared Java strategy core"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "local-jforex-parity-ordinal" "Run local JForex surrogate in ordinal mode (all 6 symbols) for Stage 14 alignment verification"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "local-jforex-parity-spotlight" "Extract event-bar tick windows and run fast surrogate alignment check (seconds vs minutes)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "local-jforex-cert" "Summarize local JForex surrogate outputs into a pre-Stage certification report"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "stage13-dukascopy-cert" "Build Stage 13 Dukascopy TestClient summary, checks, report, and snapshot"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "stage14-jforex-cert" "Build Stage 14 JForex certification summary, checks, report, and snapshot"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "full-stage14-cert" "Run outcome-parity → local-jforex-cert → stage14-jforex-cert in order (monthly recert command)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "jforex-live" "Start the JForex live/demo session for all symbols (IClient-based, live governance mode)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "demo-cert-monitor" "Start observability and print the Dukascopy demo certification monitoring URLs, metrics, and readiness file"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "freeze-oco-dukascopy-candidate" "Freeze mutable candidate governance locks to oco_dukascopy_candidate/"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "monthly-build" "Freeze a month-scoped candidate certification bundle for later recert"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "monthly-recert" "Run definitive certification against an existing month-scoped candidate build bundle"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "promote-live" "Archive a certified candidate build bundle to oco_history_dukascopy_candidate/ and print restart reminder"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "observability-up" "Start Prometheus, Alertmanager, and Grafana for API + JForex monitoring"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "account-risk-monitoring-report" "Build broker-neutral account-risk monitoring outputs"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "reconcile-account-risk-reservations" "Reconcile broker-neutral account-risk reservations"
	@printf "\n$(COLOR_SECTION)== Docs ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs" "Serve docs locally"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-build" "Build docs"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-contract" "Run docs contracts and OCO docs governance checks"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-contract-ci" "Run CI-safe docs contracts without heavy recomputation"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-clean" "Remove built site/"

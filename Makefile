.DEFAULT_GOAL := help
COLOR_RESET := \033[0m
COLOR_HEADER := \033[1;36m
COLOR_SECTION := \033[1;35m
COLOR_TARGET := \033[0;32m
COLOR_DOC := \033[0;34m
COLOR_DESC := \033[2m

# Active symbol list — single source of truth for multi-symbol targets
REBUILD_SYMBOLS := EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD

.PHONY: test docs docs-build docs-contract docs-contract-ci docs-clean precommit-install precommit-run lint format help onboard-symbol check-legacy-drift deploy-cbot provision retrain-all rebuild-all quality ty vulture smellcheck radon xenon audit-all freeze-oco freeze-oco-history validate-oco-history summarize-runtime-db-run reconcile-ctrader-run

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
	cp src/cbot/BehemothTradeManager.cs ~/cAlgo/Sources/Robots/BehemothTradeManager/BehemothTradeManager/BehemothTradeManager.cs
	@echo "Deployment complete! Please rebuild the bot in cTrader Automate."

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
	@printf "\n$(COLOR_SECTION)== Pipeline ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "retrain-all" "Re-run ML pipeline + docs for all symbols (skip data download)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "rebuild-all" "Full rebuild: data + ML + docs for all symbols (MONTHS=... required)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "freeze-oco-history" "Freeze month-scoped historical governance locks for replay/backtests"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "validate-oco-history" "Validate historical lock integrity and index coverage"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "summarize-runtime-db-run" "Summarize runtime DB rows for one symbol/window"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "reconcile-ctrader-run" "Reconcile cTrader runtime signals against research predictions"
	@printf "\n$(COLOR_SECTION)== Docs ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs" "Serve docs locally"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-build" "Build docs"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-contract" "Run docs contracts and OCO docs governance checks"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-contract-ci" "Run CI-safe docs contracts without heavy recomputation"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-clean" "Remove built site/"

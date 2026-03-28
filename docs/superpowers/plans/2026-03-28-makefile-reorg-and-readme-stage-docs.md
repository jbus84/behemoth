# Makefile Reorganization & README Stage Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the Makefile into logical sections with stage aliases and shared parameter blocks, and update the README with a stage-to-command reference table and full operator workflow.

**Architecture:** Single-file Makefile rewrite preserving all existing target behavior while adding section banners, stage alias targets, and extracted shared parameters. README gains two new sections replacing the current "Practical Release Check" section.

**Tech Stack:** GNU Make, Markdown

---

## File Structure

- Modify: `Makefile` — full reorganization (reorder targets into sections, add stage aliases, extract shared params, split `.PHONY`, rewrite `help`)
- Modify: `README.md` — add pipeline stages table, replace "Practical Release Check" with full operator workflow

---

### Task 1: Rewrite Makefile — Variables & Configuration section

**Files:**
- Modify: `Makefile:1-30`

This task replaces the top of the Makefile: the monolithic `.PHONY` line (line 24) becomes grouped multi-line declarations, and a shared `JFOREX_MATRIX_ARGS` define block is added.

- [ ] **Step 1: Replace lines 1-30 of the Makefile**

Replace the entire top section (lines 1 through 30) with:

```makefile
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

OFFSET_ROBUSTNESS_SYMBOLS_DEFAULT := EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD
OFFSET_ROBUSTNESS_OFFSETS_DEFAULT := 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99
OFFSET_ROBUSTNESS_COARSE_DEFAULT := 0,10,20,30,40,50,60,70,80,90
OFFSET_ROBUSTNESS_API_CONFIRM_DEFAULT := 0,25,50,75
OFFSET_ROBUSTNESS_WARMUP_DEFAULT := 73,145,217,289,400

# -- Shared parameter blocks ------------------------------------------------

define JFOREX_MATRIX_ARGS
	$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
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
	--metrics-port-base $(or $(METRICS_PORT_BASE),9465)
endef

# -- .PHONY declarations (grouped by section) -------------------------------

# Development
.PHONY: test test-java quality ty vulture smellcheck radon xenon \
        lint format precommit-install precommit-run check-legacy-drift

# Infrastructure
.PHONY: provision observability-up observability-down

# Stages
.PHONY: stage0 stage1 stage2 stage3 stage4 stage5 stage6 stage7 \
        stage8 stage9 stage10 stage11 stage12 stage13 stage14 \
        onboard-symbol retrain-all rebuild-all audit-all \
        freeze-oco freeze-oco-history freeze-oco-dukascopy-candidate \
        validate-oco-history stage12-api-parity \
        local-jforex-parity local-jforex-parity-matrix \
        local-jforex-parity-ordinal local-jforex-parity-spotlight \
        local-jforex-cert jforex-dukascopy-matrix \
        stage13-dukascopy-cert stage14-jforex-cert \
        full-stage14-cert jforex-outcome-parity

# Release Lifecycle
.PHONY: monthly-build monthly-recert promote-live

# Operations
.PHONY: jforex-live demo-cert-monitor

# Analysis
.PHONY: offset-robustness-study offset-frozen-screen \
        dukascopy-source-audit reconcile-historical-predictions \
        summarize-runtime-db-run account-risk-monitoring-report \
        reconcile-account-risk-reservations

# Documentation
.PHONY: docs docs-build docs-contract docs-contract-ci docs-clean

# Help
.PHONY: help
```

- [ ] **Step 2: Verify the Makefile still parses**

Run: `make -n help 2>&1 | head -5`
Expected: No syntax errors; prints the first few lines of the help target recipe.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "refactor: reorganize Makefile variables and split .PHONY declarations"
```

---

### Task 2: Rewrite Makefile — Development section

**Files:**
- Modify: `Makefile`

Move all development/quality targets into a contiguous block after the variables section. The target recipes are unchanged — only their position in the file changes.

- [ ] **Step 1: Insert section banner and move targets**

After the `.PHONY: help` line from Task 1, insert the Development section. These targets currently live at lines 42-44 (`test`), 45-46 (`test-java`), 218 (`quality`), 221-239 (`ty` through `xenon`), 484-495 (`precommit-*`, `lint`, `format`), 497-498 (`check-legacy-drift`).

Collect them into one block:

```makefile
##==============================##
##  Development                 ##
##==============================##

test:
	uv run pytest -q

test-java:
	gradle :jforex-adapter:test

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

lint:
	uv run ruff check scripts tests

format:
	uv run ruff format scripts tests

precommit-install:
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

precommit-run:
	uv run pre-commit run --all-files

check-legacy-drift:
	uv run python scripts/check_legacy_drift.py
```

- [ ] **Step 2: Verify test target**

Run: `make -n test`
Expected: Prints `uv run pytest -q` (dry run, no errors).

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "refactor: group development targets into Development section"
```

---

### Task 3: Rewrite Makefile — Infrastructure section

**Files:**
- Modify: `Makefile`

Move infrastructure targets into a contiguous block. Currently at lines 32-39.

- [ ] **Step 1: Insert section banner and targets**

After the Development section, add:

```makefile
##==============================##
##  Infrastructure              ##
##==============================##

provision:
	@echo "Provisioning Alertmanager configuration..."
	uv run python scripts/provision_observability.py

observability-up:
	docker compose up -d prometheus alertmanager grafana

observability-down:
	docker compose down
```

- [ ] **Step 2: Commit**

```bash
git add Makefile
git commit -m "refactor: group infrastructure targets into Infrastructure section"
```

---

### Task 4: Rewrite Makefile — Stages section (aliases + composite targets)

**Files:**
- Modify: `Makefile`

This is the largest section. It contains stage alias targets, then the underlying real targets grouped by stage.

- [ ] **Step 1: Insert section banner, stage aliases, and composite targets**

After the Infrastructure section, add:

```makefile
##==============================##
##  Stages (0-14)               ##
##==============================##

# -- Stage aliases -----------------------------------------------------------

stage0 stage1 stage2 stage3 stage4 stage5:
	@echo "Stages 0-5 run via 'make retrain-all' (skip data) or 'make rebuild-all MONTHS=...' (with data)."
	@echo "For a single symbol: make onboard-symbol SYMBOL=EURUSD MONTHS=201801-202602"

stage6:
	@echo "Stage 6 (tick-exact verification) runs as part of onboard-symbol when reduced core has states."
	@echo "Standalone not supported - run via make retrain-all or make rebuild-all."

stage7: audit-all

stage8:
	@echo "Stage 8 (robustness) runs as part of onboard-symbol when reduced core has states."
	@echo "Standalone not supported - run via make retrain-all or make rebuild-all."

stage9: freeze-oco

stage10:
	@echo "Stage 10 is documentation/risk tracking. See docs/strategy_bible/stage_10_known_risks_and_backlog.md"

stage11:
	@echo "Stage 11 (execution Monte Carlo) runs as part of onboard-symbol."
	@echo "Standalone not supported - run via make retrain-all or make rebuild-all."

stage12: stage12-api-parity

stage13: stage13-dukascopy-cert

stage14: stage14-jforex-cert

# -- Stages 0-11: Composite training targets ---------------------------------

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

# -- Stage 7: Logical & statistical audit ------------------------------------

audit-all:
	@echo "\n--- Running Core Audits ---"
	uv run python scripts/audit_oco_pipeline_logical_issues.py
	uv run python scripts/audit_oco_leakage_label_integrity.py
	uv run python scripts/audit_oco_execution_risk_prelive.py

# -- Stage 9: Live governance ------------------------------------------------

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

# -- Stage 12: API parity ---------------------------------------------------

stage12-api-parity:

# -- Stage 12.5: Local JForex surrogate parity -------------------------------

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
		$(JFOREX_MATRIX_ARGS) \
		--start-ts $(or $(START_TS),2025-07-07T00:00:00Z) \
		--end-ts $(or $(END_TS),2025-07-09T00:00:00Z) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks) \
		--warmup-ticks $(or $(WARMUP_TICKS),30000) \
		--lookback-days $(or $(LOOKBACK_DAYS),31) \
		--phase-bar-ticks $(or $(PHASE_BAR_TICKS),100) \
		--starting-balance $(or $(STARTING_BALANCE),100000)

local-jforex-parity-ordinal:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_local_jforex_surrogate_matrix.py \
		$(JFOREX_MATRIX_ARGS) \
		--start-ts $(or $(START_TS),2025-07-07T00:00:00Z) \
		--end-ts $(or $(END_TS),2025-07-09T00:00:00Z) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks) \
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
		$(JFOREX_MATRIX_ARGS) \
		--start-ts 2000-01-01T00:00:00Z \
		--end-ts 2030-01-01T00:00:00Z \
		--tick-root $(or $(SPOTLIGHT_DIR),data/analysis/spotlight_ticks) \
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

# -- Stage 12: Dukascopy JForex matrix (run within monthly-recert) -----------

jforex-dukascopy-matrix:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_jforex_dukascopy_matrix.py \
		$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
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
		--start-ts $(or $(START_TS),2025-07-04T00:00:00Z) \
		--end-ts $(or $(END_TS),2025-07-09T00:00:00Z) \
		--metrics-port-base $(or $(METRICS_PORT_BASE),9464)

# -- Stage 13: Dukascopy TestClient certification ----------------------------

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

# -- Stage 14: JForex runtime certification ----------------------------------

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

jforex-outcome-parity:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/reconcile_jforex_outcomes.py \
		--symbols $(SYMBOLS) \
		--lock-dir $(or $(LOCK_DIR),configs/research/governance/oco_history_dukascopy_candidate/2025-07) \
		--reconcile-dir $(or $(RECONCILE_DIR),data/analysis/backtest_reconcile) \
		--eval-start $(or $(EVAL_START),2025-07-07T00:00:00Z) \
		--eval-end $(or $(EVAL_END),2025-07-09T00:00:00Z) \
		--signal-coverage-threshold $(or $(SIGNAL_COVERAGE_THRESHOLD),1.0) \
		--out-csv $(or $(OUT_CSV),data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv)
```

- [ ] **Step 2: Verify stage alias targets**

Run: `make -n stage7 2>&1 | head -3`
Expected: Shows `audit-all` recipe commands (dry run).

Run: `make -n stage14 2>&1 | head -3`
Expected: Shows `stage14-jforex-cert` recipe commands (dry run).

Run: `make stage0 2>&1`
Expected: Prints guidance about `retrain-all` / `rebuild-all`.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "refactor: group stage targets with aliases into Stages section"
```

---

### Task 5: Rewrite Makefile — Release Lifecycle, Operations, Analysis, Documentation sections

**Files:**
- Modify: `Makefile`

Move remaining targets into their sections.

- [ ] **Step 1: Insert remaining sections**

After the Stages section, add:

```makefile
##==============================##
##  Release Lifecycle           ##
##==============================##

monthly-build:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_monthly_build.py \
		$(if $(MODEL_MONTH),--model-month "$(MODEL_MONTH)",)

monthly-recert:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_monthly_recert.py \
		$(if $(MODEL_MONTH),--model-month "$(MODEL_MONTH)",) \
		$(if $(START_TS),--start-ts "$(START_TS)",) \
		$(if $(END_TS),--end-ts "$(END_TS)",) \
		$(if $(EVAL_START),--eval-start "$(EVAL_START)",) \
		$(if $(EVAL_END),--eval-end "$(EVAL_END)",) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile)

promote-live:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_promote_live.py \
		$(if $(MODEL_MONTH),--model-month "$(MODEL_MONTH)",) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile)

##==============================##
##  Operations                  ##
##==============================##

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

##==============================##
##  Analysis                    ##
##==============================##

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

account-risk-monitoring-report:
	uv run python scripts/build_account_risk_monitoring_report.py

reconcile-account-risk-reservations:
	uv run python scripts/reconcile_account_risk_reservations.py

##==============================##
##  Documentation               ##
##==============================##

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

docs-clean:
	rm -rf site
```

- [ ] **Step 2: Verify targets**

Run: `make -n monthly-build 2>&1 | head -3`
Expected: Shows `uv run python scripts/run_monthly_build.py` (dry run).

Run: `make -n jforex-live 2>&1 | head -3`
Expected: Shows `uv run python scripts/run_jforex_live.py` (dry run).

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "refactor: add Release, Operations, Analysis, Documentation sections"
```

---

### Task 6: Rewrite Makefile — Help target

**Files:**
- Modify: `Makefile`

Rewrite the `help` target to mirror the new section structure.

- [ ] **Step 1: Insert updated help target**

After the Documentation section, add:

```makefile
##==============================##
##  Help                        ##
##==============================##

help:
	@printf "$(COLOR_HEADER)Targets:$(COLOR_RESET)\n"
	@printf "\n$(COLOR_SECTION)== Development ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "test" "Run pytest"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "test-java" "Run JForex adapter unit tests via Gradle"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "quality" "Run all quality checks (ty, lint, vulture, smellcheck, radon, xenon)"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "lint" "Run ruff lint"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "format" "Run ruff format"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "precommit-install" "Install pre-commit hooks"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "precommit-run" "Run pre-commit on all files"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "check-legacy-drift" "Check repo for legacy/forbidden code drift"
	@printf "\n$(COLOR_SECTION)== Infrastructure ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "provision" "Provision Alertmanager configuration"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "observability-up" "Start Prometheus, Alertmanager, and Grafana"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "observability-down" "Stop monitoring stack"
	@printf "\n$(COLOR_SECTION)== Stages (0-14) ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "stage0 .. stage5" "Print guidance (run via retrain-all or rebuild-all)"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "stage7" "Logical & statistical audit (alias for audit-all)"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "stage9" "Live governance freeze (alias for freeze-oco)"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "stage12" "API parity (alias for stage12-api-parity)"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "stage13" "Dukascopy TestClient cert (alias for stage13-dukascopy-cert)"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "stage14" "JForex runtime cert (alias for stage14-jforex-cert)"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "retrain-all" "Re-run ML pipeline (stages 2-11) for all symbols"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "rebuild-all" "Full rebuild incl. data (stages 0-11) MONTHS=... required"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "onboard-symbol" "Onboard a single symbol SYMBOL=... MONTHS=..."
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "audit-all" "Run pipeline logical/leakage/execution audits"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "freeze-oco" "Verify parity, refreeze governance locks, run audits"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "freeze-oco-history" "Freeze month-scoped historical governance locks"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "freeze-oco-dukascopy-candidate" "Freeze mutable candidate governance locks"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "validate-oco-history" "Validate historical lock integrity and index coverage"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "local-jforex-parity" "Single-symbol local JForex surrogate parity"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "local-jforex-parity-matrix" "Multi-symbol local JForex surrogate matrix"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "local-jforex-parity-ordinal" "Local JForex surrogate in ordinal mode"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "local-jforex-parity-spotlight" "Extract event-bar windows + fast surrogate check"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "local-jforex-cert" "Summarize local surrogate into pre-Stage cert report"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "jforex-dukascopy-matrix" "Run Dukascopy JForex replay matrix"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "stage13-dukascopy-cert" "Stage 13 Dukascopy TestClient certification"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "stage14-jforex-cert" "Stage 14 JForex runtime certification"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "full-stage14-cert" "Run outcome-parity + local-cert + stage14-cert"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "jforex-outcome-parity" "Reconcile JForex outcomes against locked predictions"
	@printf "\n$(COLOR_SECTION)== Release Lifecycle ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "monthly-build" "Freeze candidate certification bundle MODEL_MONTH=..."
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "monthly-recert" "Definitive certification (stages 12-14) MODEL_MONTH=..."
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "promote-live" "Archive certified bundle MODEL_MONTH=..."
	@printf "\n$(COLOR_SECTION)== Operations ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "jforex-live" "Start JForex live/demo session for all symbols"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "demo-cert-monitor" "Start observability and print monitoring URLs"
	@printf "\n$(COLOR_SECTION)== Analysis ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "offset-robustness-study" "Run offset tick-bar robustness study"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "offset-frozen-screen" "Run offset frozen model screen"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "dukascopy-source-audit" "Audit Dukascopy tick completeness"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "reconcile-historical-predictions" "Rebuild frozen historical predictions"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "summarize-runtime-db-run" "Summarize runtime DB rows SYMBOL=..."
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "account-risk-monitoring-report" "Build account-risk monitoring outputs"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "reconcile-account-risk-reservations" "Reconcile account-risk reservations"
	@printf "\n$(COLOR_SECTION)== Documentation ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_DOC)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs" "Serve docs locally"
	@printf "  $(COLOR_DOC)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-build" "Build docs"
	@printf "  $(COLOR_DOC)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-contract" "Run full docs contracts and governance checks"
	@printf "  $(COLOR_DOC)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-contract-ci" "Run CI-safe docs contracts"
	@printf "  $(COLOR_DOC)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-clean" "Remove built site/"
```

- [ ] **Step 2: Remove all old target definitions**

At this point, the Makefile should contain ONLY the new sections (from Tasks 1-6). Delete any remaining old target definitions that were not moved (they should all be duplicates of what's now in the sections above). The old `help` target at the bottom of the original file is replaced by this one.

- [ ] **Step 3: Verify help output**

Run: `make help`
Expected: Prints organized sections: Development, Infrastructure, Stages (0-14), Release Lifecycle, Operations, Analysis, Documentation. Each target has a description. No syntax errors.

- [ ] **Step 4: Verify all original targets still work (dry run)**

Run: `make -n test && make -n retrain-all && make -n monthly-build && make -n jforex-live && make -n docs && echo "ALL OK"`
Expected: `ALL OK` — all targets resolve without errors in dry-run mode.

- [ ] **Step 5: Commit**

```bash
git add Makefile
git commit -m "refactor: rewrite help target to mirror new section layout"
```

---

### Task 7: Update README — Pipeline Stages table and Full Operator Workflow

**Files:**
- Modify: `README.md:107-115` (replace "Practical Release Check (Short)" section)

- [ ] **Step 1: Replace the "Practical Release Check (Short)" section**

Replace lines 107-115 of `README.md` (the section starting with `## Practical Release Check (Short)`) with:

```markdown
## Pipeline Stages

| Stage | Name | Command | Notes |
|-------|------|---------|-------|
| 0 | Data Acquisition | `make rebuild-all MONTHS=...` | Downloads ticks, builds tick bars + velocity |
| 1 | Data Reliability | `make rebuild-all MONTHS=...` | Audit runs automatically within rebuild |
| 2 | Opportunity Mining | `make retrain-all` | Mine OCO candidate families |
| 3 | Monthly WFO | `make retrain-all` | CatBoost walk-forward + threshold schedules |
| 4 | Execution Realism | `make retrain-all` | Stop-limit tick-fill analysis |
| 5 | Reduced Core | `make retrain-all` | State-level governance selection |
| 6 | Tick-Exact Verification | `make retrain-all` | Runs within onboard when reduced core has states |
| 7 | Logical & Statistical Audit | `make retrain-all` | Also available standalone: `make stage7` |
| 8 | Robustness & Stress | `make retrain-all` | Runs within onboard when reduced core has states |
| 9 | Live Governance | `make stage9` | Alias for `make freeze-oco` |
| 10 | Known Risks & Backlog | -- | Documentation only; see `docs/strategy_bible/` |
| 11 | Execution Monte Carlo | `make retrain-all` | Runs within onboard pipeline |
| 12 | API Parity | `make monthly-recert` | Runs as step 1 (jforex-dukascopy-matrix) |
| 12.5 | Local JForex Surrogate | `make monthly-recert` | Runs as step 3 (local-jforex-parity-matrix) |
| 13 | Dukascopy TestClient | `make monthly-recert` | Runs as step 2 (stage13-dukascopy-cert) |
| 14 | JForex Runtime Cert | `make monthly-recert` | Runs as step 4 (full-stage14-cert) |

Individual stages can also be run standalone via `make stageN` (e.g., `make stage12`, `make stage14`).

## Full Operator Workflow

### Initial Setup (one-time)
```bash
make provision              # Configure Alertmanager
make precommit-install      # Install git hooks
```

### Monthly Release Cycle

**Step 1: Retrain models**
```bash
make retrain-all
```
Runs the following stages for all symbols:
- Stage 2: Opportunity mining
- Stage 3: Monthly WFO (CatBoost + threshold schedules)
- Stage 4: Execution realism (stop-limit tick-fill)
- Stage 5: Reduced core selection
- Stage 6: Tick-exact verification (when reduced core has states)
- Stage 7: Logical & statistical audit
- Stage 8: Robustness & stress (when reduced core has states)
- Stage 11: Execution Monte Carlo

For a full rebuild including data download (adds stages 0-1):
```bash
make rebuild-all MONTHS=201801-202602
```

**Step 2: Freeze governance (stage 9)**
```bash
make freeze-oco
```

**Step 3: Build candidate bundle**
```bash
make monthly-build MODEL_MONTH=2026-02
```
Freezes model artifacts and threshold schedules into
`configs/research/governance/oco_candidate_builds/2026-02/`.

**Step 4: Certify (stages 12-14)**
```bash
make monthly-recert MODEL_MONTH=2026-02
```
Runs the certification chain:
- Stage 12: API parity (jforex-dukascopy-matrix)
- Stage 12.5: Local JForex surrogate parity
- Stage 13: Dukascopy TestClient certification
- Stage 14: JForex runtime certification

Prints per-symbol go/no-go summary.

**Step 5: Promote**
```bash
make promote-live MODEL_MONTH=2026-02
```
Only run after `monthly-recert` is green.

**Step 6: Restart live system**
```bash
make jforex-live
```

### Ad-hoc Commands
```bash
make quality                # Run all code quality checks
make test                   # Run pytest
make docs                   # Serve docs locally
make docs-contract-ci       # Refresh governance docs
make observability-up       # Start Prometheus + Grafana
```
```

- [ ] **Step 2: Verify README renders correctly**

Open `README.md` and visually check:
- Pipeline Stages table has 17 rows (header + 16 stages including 12.5)
- Full Operator Workflow has 6 numbered steps
- All code blocks are properly fenced
- No broken markdown

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add pipeline stages table and full operator workflow to README"
```

---

### Task 8: Final verification

**Files:**
- Verify: `Makefile`, `README.md`

- [ ] **Step 1: Verify all stage aliases work**

Run each stage alias in dry-run or echo mode:

```bash
make stage0 2>&1 | grep -q "retrain-all" && echo "stage0 OK"
make stage5 2>&1 | grep -q "retrain-all" && echo "stage5 OK"
make stage6 2>&1 | grep -q "onboard-symbol" && echo "stage6 OK"
make -n stage7 2>&1 | grep -q "audit_oco_pipeline" && echo "stage7 OK"
make stage8 2>&1 | grep -q "onboard-symbol" && echo "stage8 OK"
make -n stage9 2>&1 | grep -q "freeze_oco_live" && echo "stage9 OK"
make stage10 2>&1 | grep -q "documentation" && echo "stage10 OK"
make stage11 2>&1 | grep -q "onboard-symbol" && echo "stage11 OK"
make -n stage13 2>&1 | grep -q "validate_stage13" && echo "stage13 OK"
make -n stage14 2>&1 | grep -q "validate_stage14" && echo "stage14 OK"
```

Expected: All print `OK`.

- [ ] **Step 2: Verify Makefile has no duplicate targets**

Run: `grep -E '^[a-z][a-z0-9_-]*:' Makefile | sort | uniq -d`
Expected: Empty output (no duplicate target names). Note: `stage0 stage1 stage2 stage3 stage4 stage5:` is a multi-target rule, not duplicates.

- [ ] **Step 3: Verify help output is complete**

Run: `make help 2>&1 | grep -c "=="`
Expected: 7 (one `== Section ==` banner per section: Development, Infrastructure, Stages, Release Lifecycle, Operations, Analysis, Documentation).

- [ ] **Step 4: Commit (if any fixes were needed)**

```bash
git add Makefile README.md
git commit -m "fix: address final verification issues in Makefile reorg"
```

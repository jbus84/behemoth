.DEFAULT_GOAL := help

REPO_COMMON_ROOT := $(shell dirname "$$(git rev-parse --git-common-dir)")
SHARED_ENV_FILE ?= $(REPO_COMMON_ROOT)/.env
LOAD_SHARED_ENV = if [ -f "$(SHARED_ENV_FILE)" ]; then set -a; . "$(SHARED_ENV_FILE)"; set +a; fi;

# ==============================================================================
# Variables & Configuration
# ==============================================================================

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

# Default comma-separated symbol list for targets that accept --symbols (e.g. jforex-live)
SYMBOLS ?= EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD

# .PHONY declarations — grouped by section

.PHONY: test test-java quality ty lint vulture smellcheck radon xenon format \
        precommit-install precommit-run jforex-live pr docs docs-build help

# ==============================================================================
# Development
# ==============================================================================

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
	uv run xenon --max-absolute F --max-modules C src/

lint:
	uv run ruff check scripts tests

format:
	uv run ruff format scripts tests

precommit-install:
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push
	uv run pre-commit install --hook-type commit-msg

precommit-run:
	uv run pre-commit run --all-files

# ==============================================================================
# Operations
# ==============================================================================

jforex-live:
	@$(LOAD_SHARED_ENV) env UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_jforex_live.py \
		$(if $(SYMBOLS),--symbols "$(SYMBOLS)",) \
		--api-host $(or $(API_HOST),127.0.0.1) \
		--api-port $(or $(API_PORT),8000) \
		--requested-volume-units $(or $(REQUESTED_VOLUME_UNITS),10000) \
		--tick-batch-size $(or $(TICK_BATCH_SIZE),200) \
		--order-ttl-seconds $(or $(ORDER_TTL_SECONDS),900) \
		--api-timeout-seconds $(or $(API_TIMEOUT_SECONDS),60) \
		--metrics-host $(or $(METRICS_HOST),127.0.0.1) \
		--metrics-port $(or $(METRICS_PORT),9464)

pr:
	@BRANCH=$$(git rev-parse --abbrev-ref HEAD); \
	if [ "$$BRANCH" = "main" ]; then \
		echo "ERROR: Cannot create PR from main branch. Use a worktree branch."; \
		exit 1; \
	fi; \
	echo "Pushing branch $$BRANCH..."; \
	git push -u origin HEAD; \
	TITLE=$$(git log main..HEAD --format='%s' | head -1); \
	BODY=$$(git log main..HEAD --format='- %s%n%b' | sed '/^$$/d'); \
	echo "Creating PR: $$TITLE"; \
	gh pr create --title "$$TITLE" --body "$$BODY" --fill; \
	gh pr merge --auto --squash

# ==============================================================================
# Documentation
# ==============================================================================

docs:
	uv run mkdocs serve -a 127.0.0.1:8001

docs-build:
	uv run mkdocs build

# ==============================================================================
# Help
# ==============================================================================

help:
	@printf "$(COLOR_HEADER)Targets:$(COLOR_RESET)\n"
	@printf "\n$(COLOR_SECTION)== Development ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "test" "Run pytest"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "test-java" "Run JForex adapter unit tests via Gradle"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "quality" "Run all quality checks (ty, lint, vulture, smellcheck, radon, xenon)"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "ty" "Run ty type checker"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "vulture" "Run dead code detection"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "smellcheck" "Run code smell detection"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "radon" "Run complexity analysis"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "xenon" "Run complexity enforcement"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "lint" "Run ruff lint"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "format" "Run ruff format"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "precommit-install" "Install pre-commit hooks"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "precommit-run" "Run pre-commit on all files"
	@printf "\n$(COLOR_SECTION)== Operations ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "jforex-live" "Start the JForex live/demo session for all symbols (IClient-based, process-orchestrated)"
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "pr" "Push branch, create PR, enable auto-merge"
	@printf "\n$(COLOR_SECTION)== Documentation ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_DOC)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs" "Serve docs locally"
	@printf "  $(COLOR_DOC)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-build" "Build docs"
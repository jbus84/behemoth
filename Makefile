.DEFAULT_GOAL := help
COLOR_RESET := \033[0m
COLOR_HEADER := \033[1;36m
COLOR_SECTION := \033[1;35m
COLOR_TARGET := \033[0;32m
COLOR_DOC := \033[0;34m
COLOR_DESC := \033[2m

.PHONY: test docs docs-build docs-contract docs-contract-ci docs-clean precommit-install precommit-run lint format help onboard-symbol check-legacy-drift deploy-cbot

test:
	uv run pytest -q

onboard-symbol:
	@test -n "$(SYMBOL)" || (echo "error: SYMBOL is required, e.g. make onboard-symbol SYMBOL=USDCAD MONTHS=201801-202602" && exit 1)
	uv run python scripts/onboard_symbol.py --symbol $(SYMBOL) --months $(MONTHS) $(ONBOARD_FLAGS)

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
	uv run python scripts/validate_oco_rule_universe_registry.py
	uv run python scripts/remediate_oco_monitoring_alerts.py
	uv run python scripts/build_oco_governance_explainability_report.py
	uv run python scripts/build_oco_strategy_bible.py --manifest configs/research/docs/oco_bible_manifest.yaml --strict false
	uv run python scripts/build_oco_system_reference_docs.py
	uv run python scripts/build_operator_action_report.py
	uv run python scripts/build_symbol_onboarding_playbook.py
	uv run python scripts/check_oco_docs_stage_integrity.py
	uv run python scripts/validate_oco_docs_contract.py

docs-contract-ci:
	uv run python scripts/build_docs_catalog.py
	uv run python scripts/validate_oco_rule_universe_registry.py
	uv run python scripts/remediate_oco_monitoring_alerts.py
	uv run python scripts/build_oco_governance_explainability_report.py
	uv run python scripts/build_oco_strategy_bible.py --manifest configs/research/docs/oco_bible_manifest.yaml --strict false
	uv run python scripts/build_oco_system_reference_docs.py
	uv run python scripts/build_operator_action_report.py
	uv run python scripts/check_oco_docs_stage_integrity.py
	uv run python scripts/validate_oco_docs_contract.py

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
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "lint" "Run ruff lint"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "format" "Run ruff format"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "check-legacy-drift" "Check repo for legacy/forbidden code drift"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "precommit-install" "Install pre-commit hooks"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "precommit-run" "Run pre-commit on all files"
	@printf "\n$(COLOR_SECTION)== Docs ==$(COLOR_RESET)\n"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs" "Serve docs locally"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-build" "Build docs"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-contract" "Run docs contracts and OCO docs governance checks"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-contract-ci" "Run CI-safe docs contracts without heavy recomputation"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "docs-clean" "Remove built site/"

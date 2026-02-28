.DEFAULT_GOAL := help
COLOR_RESET := \033[0m
COLOR_HEADER := \033[1;36m
COLOR_SECTION := \033[1;35m
COLOR_TARGET := \033[0;32m
COLOR_DOC := \033[0;34m
COLOR_DESC := \033[2m
.PHONY: up down logs api migrate test db docs docs-build docs-contract docs-contract-ci docs-clean docs-openapi precommit-install precommit-run lint format baselines db-backup db-restore db-restore-smoke deploy replay replay-load replay-stack replay-stack-down help

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api

api:
	uv run uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	docker compose run --rm api alembic -c services/api/alembic.ini upgrade head

migrate-local:
	alembic -c services/api/alembic.ini upgrade head

test:
	uv run pytest -q

test-postgres:
	docker compose --project-directory . -f docker-compose.yml up -d db
	POSTGRES_TEST_URL=postgresql+psycopg2://behemoth:behemoth@localhost:5432/behemoth uv run pytest -q tests/test_api_postgres_integration.py

reconcile:
	uv run python scripts/reconcile_db_vs_pipeline.py

db:
	docker compose exec db psql -U behemoth -d behemoth

docs:
	uv run mkdocs serve -a 127.0.0.1:8001

docs-build:
	uv run python scripts/export_openapi.py
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

docs-openapi:
	uv run python scripts/export_openapi.py

precommit-install:
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

precommit-run:
	uv run pre-commit run --all-files

lint:
	uv run ruff check src services scripts tests

format:
	uv run ruff format src services scripts tests

baselines:
	uv run python scripts/build_baselines.py

db-backup:
	mkdir -p backups
	docker compose --project-directory . -f docker-compose.yml exec -T db pg_dump -U behemoth -d behemoth > backups/behemoth_$(shell date +%Y%m%d_%H%M%S).sql

db-restore:
	@if [ -z "$(BACKUP_FILE)" ]; then echo "BACKUP_FILE is required"; exit 1; fi
	docker compose --project-directory . -f docker-compose.yml exec -T db psql -U behemoth -d behemoth < $(BACKUP_FILE)

db-restore-smoke:
	python scripts/db_backup_restore_smoke.py

REPLAY_PROJECT ?= behemoth_replay
REPLAY_DB_PORT ?= 5433
REPLAY_DB_URL ?= postgresql+psycopg2://behemoth:behemoth@localhost:$(REPLAY_DB_PORT)/behemoth
REPLAY_API_PORT ?= 8001
REPLAY_PROM_PORT ?= 9091
REPLAY_GRAFANA_PORT ?= 3001
REPLAY_REDIS_PORT ?= 6380
REPLAY_REDIS_URL ?= redis://localhost:$(REPLAY_REDIS_PORT)/0
REPLAY_COMMIT_EVERY ?= 5000
REPLAY_SLEEP ?= 0.0
REPLAY_LIMIT ?=
REPLAY_BARS ?= m15
REPLAY_API_LIMIT ?= 5000
REPLAY_PROGRESS_EVERY ?= 1000
REPLAY_ENFORCE_RISK ?= 1
REPLAY_GUARDRAIL ?= 1
REPLAY_REPORT ?= data/analysis/replay_report.json
REPLAY_API_URL ?= http://localhost:$(REPLAY_API_PORT)
REPLAY_COMPOSE = -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.replay.yml

deploy:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

replay:
	docker compose --project-directory . -f docker-compose.yml --project-name $(REPLAY_PROJECT) down -v >/dev/null 2>&1 || true
	DB_PORT=$(REPLAY_DB_PORT) docker compose --project-directory . -f docker-compose.yml --project-name $(REPLAY_PROJECT) up -d db
	@until docker compose --project-directory . -f docker-compose.yml --project-name $(REPLAY_PROJECT) exec -T db pg_isready -U behemoth >/dev/null 2>&1; do \
		printf "Waiting for db...\\n"; \
		sleep 1; \
	done
	@docker compose --project-directory . -f docker-compose.yml --project-name $(REPLAY_PROJECT) exec -T db psql -U behemoth -d behemoth -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
	DATABASE_URL=$(REPLAY_DB_URL) uv run alembic -c services/api/alembic.ini upgrade head
	REPLAY_REDIS_URL=$(REPLAY_REDIS_URL) DATABASE_URL=$(REPLAY_DB_URL) uv run python scripts/replay_pipeline_to_db.py --bars $(REPLAY_BARS) --reset --commit-every $(REPLAY_COMMIT_EVERY) --sleep $(REPLAY_SLEEP) $(if $(REPLAY_LIMIT),--limit $(REPLAY_LIMIT),) --report $(REPLAY_REPORT) $(if $(filter 0,$(REPLAY_ENFORCE_RISK)),--no-enforce-risk,) $(if $(filter 0,$(REPLAY_GUARDRAIL)),--no-guardrail,)

replay-load:
	@until docker compose --project-directory . $(REPLAY_COMPOSE) --project-name $(REPLAY_PROJECT) exec -T db pg_isready -U behemoth >/dev/null 2>&1; do \
		printf "Waiting for replay db...\\n"; \
		sleep 1; \
	done
	@docker compose --project-directory . $(REPLAY_COMPOSE) --project-name $(REPLAY_PROJECT) exec -T db psql -U behemoth -d behemoth -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
	DATABASE_URL=$(REPLAY_DB_URL) uv run alembic -c services/api/alembic.ini upgrade head
	REPLAY_REDIS_URL=$(REPLAY_REDIS_URL) REPLAY_API_URL=$(REPLAY_API_URL) uv run python scripts/replay_bars_via_api.py --bars $(REPLAY_BARS) --sleep $(REPLAY_SLEEP) --progress-every $(REPLAY_PROGRESS_EVERY) --api-limit $(REPLAY_API_LIMIT) $(if $(REPLAY_LIMIT),--limit $(REPLAY_LIMIT),)
replay-stack:
	DB_PORT=$(REPLAY_DB_PORT) API_PORT=$(REPLAY_API_PORT) PROM_PORT=$(REPLAY_PROM_PORT) GRAFANA_PORT=$(REPLAY_GRAFANA_PORT) REDIS_PORT=$(REPLAY_REDIS_PORT) \
	docker compose --project-directory . $(REPLAY_COMPOSE) --project-name $(REPLAY_PROJECT) up -d --build
	@printf "Replay stack running:\\n"
	@printf "  API:       http://localhost:$(REPLAY_API_PORT)\\n"
	@printf "  Prometheus http://localhost:$(REPLAY_PROM_PORT)\\n"
	@printf "  Grafana:   http://localhost:$(REPLAY_GRAFANA_PORT) (admin/admin)\\n"

replay-stack-down:
	docker compose --project-directory . $(REPLAY_COMPOSE) --project-name $(REPLAY_PROJECT) down -v

help:
	@printf "$(COLOR_HEADER)Targets:$(COLOR_RESET)\\n"
	@printf "\\n$(COLOR_SECTION)== Core Services ==$(COLOR_RESET)\\n"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "up" "Start docker compose services"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "down" "Stop docker compose services"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "logs" "Tail API logs"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "api" "Run API locally (uvicorn reload)"
	@printf "\\n$(COLOR_SECTION)== Database ==$(COLOR_RESET)\\n"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "migrate" "Run DB migrations (compose)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "migrate-local" "Run DB migrations (local)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "db" "Open psql shell (compose)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "db-backup" "Create DB backup to backups/"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "db-restore" "Restore DB backup (BACKUP_FILE=...)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "db-restore-smoke" "Backup/restore smoke test"
	@printf "\\n$(COLOR_SECTION)== Quality ==$(COLOR_RESET)\\n"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "test" "Run pytest"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "test-postgres" "Run API postgres integration test"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "lint" "Run ruff lint"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "format" "Run ruff format"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "precommit-install" "Install pre-commit hooks"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "precommit-run" "Run pre-commit on all files"
	@printf "\\n$(COLOR_SECTION)== Docs ==$(COLOR_RESET)\\n"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "docs" "Serve docs locally"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "docs-build" "Build docs (export OpenAPI first)"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "docs-contract" "Run docs contracts and OCO docs governance checks"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "docs-contract-ci" "Run CI-safe docs contracts without heavy recomputation"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "docs-clean" "Remove built site/"
	@printf "  $(COLOR_DOC)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "docs-openapi" "Export OpenAPI spec only"
	@printf "\\n$(COLOR_SECTION)== Data & Analysis ==$(COLOR_RESET)\\n"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "baselines" "Generate M5/M15 baseline snapshots"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "replay" "Fast DB-only replay from event CSVs (bars=$(REPLAY_BARS), isolated temp DB @ :$(REPLAY_DB_PORT))"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "replay-load" "Full end-to-end replay via API + DB (bars=$(REPLAY_BARS), updates Grafana live)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "replay-stack" "Run isolated replay stack (DB/API/Prom/Grafana) on alt ports"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "replay-stack-down" "Stop isolated replay stack"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "reconcile" "Compare DB vs pipeline outputs"
	@printf "\\n$(COLOR_SECTION)== Deployment ==$(COLOR_RESET)\\n"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\\n" "deploy" "Start prod-like stack (compose + prod overlay)"

deploy-cbot: ## Deploy cBot code to cTrader Robots directory
	python3 scripts/deploy_cbot.py

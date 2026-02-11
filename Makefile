.PHONY: up down logs api migrate test db docs docs-build docs-clean docs-openapi precommit-install precommit-run lint format baselines db-backup db-restore db-restore-smoke deploy

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
	docker compose up -d db
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
	docker compose exec -T db pg_dump -U behemoth -d behemoth > backups/behemoth_$(shell date +%Y%m%d_%H%M%S).sql

db-restore:
	@if [ -z "$(BACKUP_FILE)" ]; then echo "BACKUP_FILE is required"; exit 1; fi
	docker compose exec -T db psql -U behemoth -d behemoth < $(BACKUP_FILE)

db-restore-smoke:
	python scripts/db_backup_restore_smoke.py

deploy:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

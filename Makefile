.PHONY: up down logs api migrate test db

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

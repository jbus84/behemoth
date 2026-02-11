# Makefile Reference

This Makefile is the operational entrypoint for local dev, tests, and ops.
Run `make help` to list all targets.

## Core Targets

- `make up`: start docker compose services (dev stack)
- `make down`: stop docker compose services
- `make deploy`: start prod‑like stack (compose + prod overlay)
- `make logs`: tail API logs
- `make api`: run API locally (uvicorn reload)
- `make migrate`: run Alembic migrations in compose
- `make migrate-local`: run migrations locally

## Testing & Quality

- `make test`: run pytest
- `make test-postgres`: run Postgres integration tests
- `make lint`: run ruff lint
- `make format`: run ruff format
- `make precommit-run`: run all pre-commit hooks

## Data & Baselines

- `make baselines`: generate M5/M15 golden baselines
- `make replay`: replay historical trades into DB (for dashboards)

## Docs

- `make docs`: serve MkDocs locally
- `make docs-build`: build MkDocs (exports OpenAPI first)

## DB Ops

- `make db-backup`: create a DB backup in `backups/`
- `make db-restore BACKUP_FILE=...`: restore a backup
- `make db-restore-smoke`: backup/restore smoke test

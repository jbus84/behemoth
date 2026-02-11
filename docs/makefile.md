# Makefile Reference

Use `make help` to list targets.

**Legend**
- <span style="color:#1f77b4;"><strong>Target</strong></span>
- <span style="color:#2ca02c;"><strong>Documentation</strong></span>

**Core**
- <span style="color:#1f77b4;"><strong>`make up`</strong></span>
  <span style="color:#2ca02c;">Start docker compose services (dev stack).</span>
- <span style="color:#1f77b4;"><strong>`make down`</strong></span>
  <span style="color:#2ca02c;">Stop docker compose services.</span>
- <span style="color:#1f77b4;"><strong>`make deploy`</strong></span>
  <span style="color:#2ca02c;">Start prod‑like stack (compose + prod overlay).</span>
- <span style="color:#1f77b4;"><strong>`make logs`</strong></span>
  <span style="color:#2ca02c;">Tail API logs.</span>
- <span style="color:#1f77b4;"><strong>`make api`</strong></span>
  <span style="color:#2ca02c;">Run API locally (uvicorn reload).</span>
- <span style="color:#1f77b4;"><strong>`make migrate`</strong></span>
  <span style="color:#2ca02c;">Run Alembic migrations in compose.</span>
- <span style="color:#1f77b4;"><strong>`make migrate-local`</strong></span>
  <span style="color:#2ca02c;">Run migrations locally.</span>

**Testing & Quality**
- <span style="color:#1f77b4;"><strong>`make test`</strong></span>
  <span style="color:#2ca02c;">Run pytest.</span>
- <span style="color:#1f77b4;"><strong>`make test-postgres`</strong></span>
  <span style="color:#2ca02c;">Run Postgres integration tests.</span>
- <span style="color:#1f77b4;"><strong>`make lint`</strong></span>
  <span style="color:#2ca02c;">Run ruff lint.</span>
- <span style="color:#1f77b4;"><strong>`make format`</strong></span>
  <span style="color:#2ca02c;">Run ruff format.</span>
- <span style="color:#1f77b4;"><strong>`make precommit-run`</strong></span>
  <span style="color:#2ca02c;">Run all pre‑commit hooks.</span>

**Data & Baselines**
- <span style="color:#1f77b4;"><strong>`make baselines`</strong></span>
  <span style="color:#2ca02c;">Generate M5/M15 golden baselines.</span>
- <span style="color:#1f77b4;"><strong>`make replay`</strong></span>
  <span style="color:#2ca02c;">Replay historical trades into DB (dashboards).</span>

**Docs**
- <span style="color:#1f77b4;"><strong>`make docs`</strong></span>
  <span style="color:#2ca02c;">Serve MkDocs locally.</span>
- <span style="color:#1f77b4;"><strong>`make docs-build`</strong></span>
  <span style="color:#2ca02c;">Build docs (exports OpenAPI first).</span>

**DB Ops**
- <span style="color:#1f77b4;"><strong>`make db-backup`</strong></span>
  <span style="color:#2ca02c;">Create a DB backup in `backups/`.</span>
- <span style="color:#1f77b4;"><strong>`make db-restore BACKUP_FILE=...`</strong></span>
  <span style="color:#2ca02c;">Restore a backup into the DB.</span>
- <span style="color:#1f77b4;"><strong>`make db-restore-smoke`</strong></span>
  <span style="color:#2ca02c;">Backup/restore smoke test.</span>

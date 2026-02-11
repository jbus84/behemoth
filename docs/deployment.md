# Deployment & Ops

## Docker Compose (Prod-Like)
Use the production overlay to run API, Postgres, and Redis:

```bash
make deploy
```

This uses `docker-compose.yml` plus `docker-compose.prod.yml` for prod‑like settings.

## Migrations
Apply migrations after deploy:

```bash
make migrate
```

## Backups
Create a snapshot (SQL dump) inside `backups/`:

```bash
make db-backup
```

Restore from a specific backup file:

```bash
make db-restore BACKUP_FILE=backups/<file>.sql
```

Smoke test the backup/restore flow (creates a temporary DB):

```bash
make db-restore-smoke
```

## Redis Optionality
If you want to disable Redis, set in config:

```yaml
enable_redis: false
```

API behavior remains correct; Redis only accelerates read paths.

## Metrics
Prometheus metrics are exposed at:

```
GET /metrics
```

Disable with `metrics_enabled: false`.

## Prometheus + Grafana
The prod compose overlay includes Prometheus and Grafana:

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (default admin/admin)

Grafana is pre‑provisioned with the Prometheus datasource from:

- `configs/grafana/datasources/datasource.yml`

Grafana dashboards are provisioned from:

- `configs/grafana/dashboards/behemoth_overview.json`
- `configs/grafana/dashboards/dashboard.yml`

Prometheus scrape config lives at:

- `configs/prometheus.yml`

## Kill Switches
Manual halt and resume:

```
POST /risk/{strategy_id}/halt
POST /risk/{strategy_id}/resume
```

## Historical Replay
To replay historical trades into the DB and visualize progress in Grafana:

```bash
export DATABASE_URL=postgresql+psycopg2://behemoth:behemoth@localhost:5432/behemoth
uv run python scripts/replay_pipeline_to_db.py --bars m5,m15 --reset --sleep 0.1
```

The replay enforces guardrail + risk gates by default and writes a report to
`data/analysis/replay_report.json`.

Automatic halts are applied via risk limits in `configs/api.yaml`.

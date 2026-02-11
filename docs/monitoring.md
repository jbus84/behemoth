# Monitoring

## Metrics
Prometheus metrics are exposed at `GET /metrics` when `metrics_enabled: true`.

Key metrics include:

- Request volume and latency: `behemoth_http_requests_total`, `behemoth_http_request_duration_seconds`
- Guardrail blocks: `behemoth_guardrail_blocks_total`
- Risk halts: `behemoth_risk_halts_total`
- Active positions: `behemoth_positions_active_total`, `behemoth_positions_active_by_pair`
- Guardrail pauses: `behemoth_guardrail_paused_total`, `behemoth_guardrail_paused_by_pair`
- Account state: `behemoth_account_equity`, `behemoth_account_peak_equity`,
  `behemoth_account_day_start_equity`, `behemoth_account_consecutive_losses`,
  `behemoth_account_halted`

## Grafana Dashboard
The `Behemoth Overview` dashboard is provisioned automatically in Grafana.
It shows:

- API request rate and p95 latency
- Active positions
- Guardrail paused pairs
- Account equity and peak equity
- Halted state and consecutive losses
- Active positions by pair

Grafana URL: `http://localhost:3000` (admin/admin)
Prometheus URL: `http://localhost:9090`

## Historical Replay (Dashboard Activity)
To replay historical trades into the DB and watch dashboards update:

```bash
export DATABASE_URL=postgresql+psycopg2://behemoth:behemoth@localhost:5432/behemoth
uv run python scripts/replay_pipeline_to_db.py --bars m5,m15 --reset --sleep 0.1
```

This streams trades into the API DB, updates guardrail/account state, and
populates live metrics that Grafana displays. The `--sleep` flag slows the
replay so the dashboard visibly updates.

By default, the replay enforces risk gates and guardrail logic and writes a
JSON report to `data/analysis/replay_report.json`.

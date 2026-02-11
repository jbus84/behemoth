# Config Reference

All runtime settings for the API live in `configs/api.yaml`.
Environment variables **override** YAML values.

## Core

| Key | Default | Meaning |
|---|---|---|
| `database_url` | `postgresql+psycopg2://behemoth:behemoth@localhost:5432/behemoth` | Postgres URL |
| `redis_url` | `redis://localhost:6379/0` | Redis URL |
| `enable_redis` | `true` | Use Redis cache |
| `auto_create_tables` | `false` | Auto-create tables (dev only) |

## Guardrail

| Key | Default |
|---|---|
| `guardrail_enabled` | `true` |
| `guardrail_loss_threshold` | `0.0` |
| `guardrail_loss_streak` | `3` |
| `guardrail_cooldown_days` | `7` |

## Risk Controls

| Key | Default |
|---|---|
| `account_equity_start` | `100000` |
| `max_daily_loss_pct` | `0.05` |
| `max_dd_pct` | `0.10` |
| `max_consecutive_losses` | `5` |
| `max_total_exposure_pct` | `1.0` |
| `max_pair_exposure_pct` | `0.10` |
| `max_weight_overshoot_pct` | `0.10` |
| `pair_weights_path` | `configs/pair_weights.yaml` |

## Example YAML

```yaml
guardrail_loss_streak: 3
guardrail_cooldown_days: 7
max_daily_loss_pct: 0.05
max_dd_pct: 0.10
max_pair_exposure_pct: 0.10
pair_weights_path: configs/pair_weights.yaml
```

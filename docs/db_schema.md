# Database Schema

This schema is defined by SQLAlchemy models in `services/api/models.py` and migrations in `services/api/migrations/versions/`.

## positions

| Column | Type | Notes |
|---|---|---|
| id | string | primary key |
| strategy_id | string | strategy label |
| pair | string | e.g., `EUR/GBP` |
| side | enum | `LONG` / `SHORT` |
| active_leg | enum | `X` / `Y` |
| status | enum | `PENDING`, `OPEN`, `CLOSING`, `CLOSED`, `CANCELLED`, `FAILED` |
| entry_ts | timestamp | |
| exit_ts | timestamp | |
| entry_price | float | |
| exit_price | float | |
| size | float | requested notional |
| notional_usd | float | stored notional |
| alloc_frac | float | fraction of equity at entry |
| entry_equity | float | equity at entry |
| pnl_bps | float | per‑trade bps |
| metadata | json | extra payload |
| version | int | optimistic version |
| created_at | timestamp | |
| updated_at | timestamp | |

Indexes:
- `ix_positions_pair_status`
- `ix_positions_exit_ts`

## orders

| Column | Type | Notes |
|---|---|---|
| id | string | primary key |
| position_id | string | FK → positions |
| status | enum | `NEW`, `SUBMITTED`, `FILLED`, `CANCELLED`, `FAILED` |
| order_type | enum | `MARKET`, `LIMIT`, `STOP` |
| qty | float | |
| price | float | |
| slippage_bps | float | |
| created_at | timestamp | |
| updated_at | timestamp | |

Index:
- `ix_orders_position_id`

## position_events

| Column | Type | Notes |
|---|---|---|
| id | string | primary key |
| position_id | string | FK → positions |
| event_type | string | `CREATED`, `OPENED`, `CLOSED`, etc. |
| payload | json | request payload |
| created_at | timestamp | |

Index:
- `ix_position_events_position_id`

## idempotency_keys

| Column | Type | Notes |
|---|---|---|
| id | string | primary key |
| key | string | unique |
| request_hash | string | hash of payload |
| position_id | string | FK → positions |
| created_at | timestamp | |

## guardrail_state

| Column | Type | Notes |
|---|---|---|
| id | string | primary key |
| strategy_id | string | |
| pair | string | |
| loss_streak | int | |
| pause_until | timestamp | |
| created_at | timestamp | |
| updated_at | timestamp | |

Unique:
- `uq_guardrail_state` on (`strategy_id`, `pair`)

Indexes:
- `ix_guardrail_state_strategy_id`
- `ix_guardrail_state_pair`

## account_state

| Column | Type | Notes |
|---|---|---|
| id | string | primary key |
| strategy_id | string | unique |
| equity | float | current |
| peak_equity | float | high water mark |
| day_start_equity | float | day‑start equity |
| day_start_date | date | day boundary |
| consecutive_losses | int | |
| halted | boolean | kill‑switch state |
| halt_reason | string | |
| created_at | timestamp | |
| updated_at | timestamp | |

Unique:
- `uq_account_state_strategy` on `strategy_id`

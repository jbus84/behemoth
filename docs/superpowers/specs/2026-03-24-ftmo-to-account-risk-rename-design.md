# FTMO → account_risk Rename — Design Spec

**Date:** 2026-03-24
**Status:** Approved

---

## Problem

The account risk management system (daily loss limits, drawdown guards, position reservations, allocator events) is fully operational but carries legacy `ftmo_*` naming throughout — DB tables, state.py methods, server.py endpoints/models, config files, and tests. `ftmo` is the name of a specific prop trading firm that is no longer in use. The naming is misleading and will confuse anyone reading the codebase.

The underlying Python modules already use `account_risk` naming (`src/behemoth/risk/account.py`, `AccountRiskProfile`, `evaluate_account_risk_limits`). This rename closes the gap.

---

## Goal

Replace all `ftmo` / `FTMO` identifiers with `account_risk` / `AccountRisk` / `ACCOUNT_RISK` throughout the codebase. DB tables are renamed in the schema definition (safe because the live DB was wiped on 2026-03-24). No migration script is required.

---

## Rename Map

### DB Tables (`src/behemoth/runtime/state.py`)

| Old | New |
|-----|-----|
| `ftmo_account_snapshots` | `account_risk_snapshots` |
| `ftmo_risk_reservations` | `account_risk_reservations` |
| `ftmo_allocator_events` | `account_risk_allocator_events` |

All inline SQL strings referencing these table names (`INSERT INTO ftmo_*`, `FROM ftmo_*`, `UPDATE ftmo_*`) must be updated alongside the `CREATE TABLE` definitions.

### `src/behemoth/risk/ftmo.py` → merged into `src/behemoth/risk/account.py`

`account.py` currently imports and re-exports everything from `ftmo.py` — it contains zero standalone logic. `ftmo.py` is the actual implementation, containing all dataclasses (`FtmoBuffers`, `FtmoCostGate`, `FtmoAllocator`, `FtmoProfile`) and functions (`load_ftmo_profile`, `evaluate_account_limits`, `evaluate_trade_guard`, `trading_day_id`, `_to_utc`, `_normalize_trade_cost_gate_mode`).

Migration steps:
1. Move all content from `ftmo.py` into `account.py`
2. Rename `FtmoProfile` → `AccountRiskProfile`, `FtmoBuffers` → `AccountRiskBuffers`, `FtmoCostGate` → `AccountRiskCostGate`, `FtmoAllocator` → `AccountRiskAllocator` within `account.py`
3. Rename functions: `load_ftmo_profile` → `load_account_risk_profile`, `evaluate_account_limits` → `evaluate_account_risk_limits`
4. Delete `ftmo.py`

### `src/behemoth/core/schemas.py`

`FtmoAccountSnapshotRequest` → `AccountRiskSnapshotRequest`

### `src/behemoth/api/server.py`

**AppConfig fields:**

| Old | New |
|-----|-----|
| `ftmo_enabled` | `account_risk_enabled` |
| `ftmo_rules_path` | `account_risk_rules_path` |
| `ftmo_profile_id` | `account_risk_profile_id` |
| `ftmo_trade_cost_gate_mode` | `account_risk_trade_cost_gate_mode` |
| `ftmo_enforce_blocks` | `account_risk_enforce_blocks` |
| `ftmo_pending_reservation_ttl_sec` | `account_risk_pending_reservation_ttl_sec` |
| `ftmo_fx_rate_max_age_sec` | `account_risk_fx_rate_max_age_sec` |

**Module-level variables and helpers:**

| Old | New |
|-----|-----|
| `_ftmo_profile` | `_account_risk_profile` |
| `load_ftmo_profile` alias | removed — call `load_account_risk_profile` directly |
| `_resolve_ftmo_account_eval()` | `_resolve_account_risk_eval()` |

**Pydantic models:**

| Old | New |
|-----|-----|
| `FtmoLimitsResponse` | `AccountRiskLimitsResponse` |
| `FtmoStatusResponse` | `AccountRiskStatusResponse` |
| `FtmoReservationsStatusResponse` | `AccountRiskReservationsStatusResponse` |
| `FtmoReservationReleaseRequest` | `AccountRiskReservationReleaseRequest` |

**Endpoints:**

| Old | New |
|-----|-----|
| `POST /risk/ftmo/snapshot` | `POST /risk/account_risk/snapshot` |
| `GET /risk/ftmo/limits` | `GET /risk/account_risk/limits` |
| `GET /risk/ftmo/status` | `GET /risk/account_risk/status` |
| `GET /risk/ftmo/reservations/status` | `GET /risk/account_risk/reservations/status` |
| `POST /risk/ftmo/reservations/release` | `POST /risk/account_risk/reservations/release` |

**`risk_metrics_snapshot` dict keys** (raw Python dict inside `_build_predictions`):

| Old | New |
|-----|-----|
| `ftmo_enabled` | `account_risk_enabled` |
| `ftmo_enabled_effective` | `account_risk_enabled_effective` |
| `ftmo_enabled_override` | `account_risk_enabled_override` |
| `ftmo_mode_source` | `account_risk_mode_source` |
| `ftmo_allow_trading` | `account_risk_allow_trading` |
| `ftmo_account_block_reason` | `account_risk_account_block_reason` |
| `ftmo_profile_id` | `account_risk_profile_id` |
| `ftmo_trade_cost_gate_mode` | `account_risk_trade_cost_gate_mode` |

**PredictRequest fields:**

| Old | New |
|-----|-----|
| `ftmo_enabled_override` | `account_risk_enabled_override` |

**Prometheus metric names** — rename to match new naming convention:

| Old | New |
|-----|-----|
| `behemoth_ftmo_daily_loss_headroom` | `behemoth_account_risk_daily_loss_headroom` |
| `behemoth_ftmo_max_loss_headroom` | `behemoth_account_risk_max_loss_headroom` |
| `behemoth_ftmo_reserved_loss_ccy` | `behemoth_account_risk_reserved_loss_ccy` |
| `behemoth_ftmo_allocator_blocks_total` | `behemoth_account_risk_allocator_blocks_total` |
| `behemoth_ftmo_allocator_admitted_total` | `behemoth_account_risk_allocator_admitted_total` |

Note: No external Prometheus/Grafana dashboards are currently configured for this system in production (monitoring infra is local). Renaming these metrics is safe.

### `src/behemoth/runtime/state.py`

All `ftmo_*` method names renamed to `account_risk_*`:

| Old | New |
|-----|-----|
| `record_ftmo_account_snapshot()` | `record_account_risk_snapshot()` |
| `get_latest_ftmo_account_snapshot()` | `get_latest_account_risk_snapshot()` |
| `get_ftmo_snapshots_since()` | `get_account_risk_snapshots_since()` |
| `create_ftmo_risk_reservation()` | `create_account_risk_reservation()` |
| `promote_ftmo_risk_reservation()` | `promote_account_risk_reservation()` |
| `release_ftmo_risk_reservation()` | `release_account_risk_reservation()` |
| `expire_stale_ftmo_pending_reservations()` | `expire_stale_account_risk_pending_reservations()` |
| `sum_active_ftmo_reserved_loss_ccy()` | `sum_active_account_risk_reserved_loss_ccy()` |
| `list_active_ftmo_risk_reservations()` | `list_active_account_risk_reservations()` |
| `log_ftmo_allocator_event()` | `log_account_risk_allocator_event()` |

### Config / Governance

| Old | New |
|-----|-----|
| `configs/research/governance/ftmo/ftmo_rules.yaml` | `configs/research/governance/account_risk/account_risk_rules.yaml` |

The default path string literals in `server.py` (`AppConfig` fields) and in `tests/test_account_risk.py` must be updated alongside this directory rename.

### Scripts

`scripts/build_account_risk_monitoring_report.py` and `scripts/reconcile_account_risk_reservations.py` are currently thin shim wrappers that import from `build_ftmo_allocator_monitoring_report.py` and `reconcile_ftmo_reservations.py` respectively. As part of this sub-project:

1. Rewrite `build_account_risk_monitoring_report.py` as a standalone implementation (move the real logic from `build_ftmo_allocator_monitoring_report.py` into it, rename identifiers)
2. Rewrite `reconcile_account_risk_reservations.py` as a standalone implementation (move the real logic from `reconcile_ftmo_reservations.py` into it, rename identifiers)
3. Delete `scripts/build_ftmo_allocator_monitoring_report.py`
4. Delete `scripts/reconcile_ftmo_reservations.py`

Also update `scripts/run_jforex_live.py` and `scripts/inject_live_observability_data.py` for any `ftmo_*` references.

### Makefile

| Old | New |
|-----|-----|
| `--ftmo-enabled-override` | `--account-risk-enabled-override` |
| `--ftmo-rules-path` | `--account-risk-rules-path` |
| `--ftmo-profile-id` | `--account-risk-profile-id` |
| `--ftmo-phase-mode` | `--account-risk-phase-mode` |
| `--ftmo-economics-mode` | `--account-risk-economics-mode` |
| `--ftmo-trade-cost-gate-mode` | `--account-risk-trade-cost-gate-mode` |
| `FTMO_ENABLED_OVERRIDE` | `ACCOUNT_RISK_ENABLED_OVERRIDE` |
| `FTMO_RULES_PATH` | `ACCOUNT_RISK_RULES_PATH` |
| `FTMO_PROFILE_ID` | `ACCOUNT_RISK_PROFILE_ID` |
| `FTMO_PHASE_MODE` | `ACCOUNT_RISK_PHASE_MODE` |
| `FTMO_ECONOMICS_MODE` | `ACCOUNT_RISK_ECONOMICS_MODE` |
| `FTMO_TRADE_COST_GATE_MODE` | `ACCOUNT_RISK_TRADE_COST_GATE_MODE` |

### Tests

| File | Action |
|------|--------|
| `tests/test_account_risk.py` | Update method calls, field names, config path (`ftmo/ftmo_rules.yaml` → `account_risk/account_risk_rules.yaml`) |
| `tests/test_api_server.py` | Update endpoint paths (`/ftmo/*` → `/account_risk/*`), model names, field names including `risk_metrics_snapshot` dict keys |
| `tests/test_duckdb_state.py` | Update method calls, table name references |
| `tests/test_diagnose_live_performance_gap.py` | Update any `ftmo_*` table references |

---

## What Does NOT Change

- The functional behaviour of the account risk system is unchanged
- `scripts/build_oco_system_reference_docs.py` — references to `ftmo_metrics` etc. are internal variable names; output column names in generated CSVs are out-of-scope for this rename (no downstream consumers depend on them)

---

## DB Migration

No migration required. The live database was wiped on 2026-03-24 before this rename. The new table names will be created on first `StateManager` initialisation.

---

## Testing

Success criterion: `pytest tests/` passes after rename with no failures. The test count is unchanged from the post-Sub-project-A baseline.

---

## Files Changed

| File | Action |
|------|--------|
| `src/behemoth/risk/ftmo.py` | Delete (content migrated to `account.py`) |
| `src/behemoth/risk/account.py` | Absorb all logic from `ftmo.py`; rename all classes/functions |
| `src/behemoth/core/schemas.py` | Rename `FtmoAccountSnapshotRequest` → `AccountRiskSnapshotRequest` |
| `src/behemoth/runtime/state.py` | Rename DB tables (+ inline SQL) + all method names |
| `src/behemoth/api/server.py` | Rename endpoints, models, config fields, module vars, dict keys, Prometheus metrics |
| `scripts/build_account_risk_monitoring_report.py` | Rewrite as standalone (absorb from `build_ftmo_allocator_monitoring_report.py`) |
| `scripts/reconcile_account_risk_reservations.py` | Rewrite as standalone (absorb from `reconcile_ftmo_reservations.py`) |
| `scripts/build_ftmo_allocator_monitoring_report.py` | Delete |
| `scripts/reconcile_ftmo_reservations.py` | Delete |
| `scripts/run_jforex_live.py` | Update any `ftmo_*` CLI args or references |
| `scripts/inject_live_observability_data.py` | Update `ftmo_*` references |
| `scripts/simulate_api_e2e_replay.py` | Update endpoint paths |
| `configs/research/governance/ftmo/` | Rename directory + file |
| `Makefile` | Rename variables and flags |
| `tests/test_account_risk.py` | Update method calls, field names, config path |
| `tests/test_api_server.py` | Update endpoint paths, model names, dict keys |
| `tests/test_duckdb_state.py` | Update method calls, table references |
| `tests/test_diagnose_live_performance_gap.py` | Update table references |

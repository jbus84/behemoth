# FTMO → account_risk Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all `ftmo` / `FTMO` identifiers with `account_risk` / `AccountRisk` / `ACCOUNT_RISK` throughout the codebase — DB tables, state methods, server endpoints, schemas, scripts, config, Makefile, and tests — leaving `pytest tests/` green with identical test count.

**Architecture:** Merge `src/behemoth/risk/ftmo.py` into `src/behemoth/risk/account.py` (rename classes/functions), rename all downstream callsites, rename the governance config directory, convert two shim wrapper scripts into standalone implementations (absorbing logic from deleted ftmo scripts), and update all tests. No functional behaviour changes.

**Tech Stack:** Python, DuckDB, FastAPI, pytest, Make

---

## File Map

| File | Action |
|------|--------|
| `src/behemoth/risk/ftmo.py` | Delete (content migrated to account.py) |
| `src/behemoth/risk/account.py` | Absorb all logic from ftmo.py; rename all classes/functions |
| `src/behemoth/core/schemas.py` | Rename `FtmoAccountSnapshotRequest` → `AccountRiskSnapshotRequest` |
| `src/behemoth/runtime/state.py` | Rename DB tables + SQL strings + all `ftmo_*` method names |
| `src/behemoth/api/server.py` | Rename AppConfig fields, module vars, Pydantic models, endpoints, dict keys, Prometheus metrics |
| `scripts/build_account_risk_monitoring_report.py` | Rewrite as standalone (absorb from build_ftmo_allocator_monitoring_report.py) |
| `scripts/reconcile_account_risk_reservations.py` | Rewrite as standalone (absorb from reconcile_ftmo_reservations.py) |
| `scripts/build_ftmo_allocator_monitoring_report.py` | Delete |
| `scripts/reconcile_ftmo_reservations.py` | Delete |
| `scripts/inject_live_observability_data.py` | Rename `ftmo_enabled_override` key; update endpoint paths |
| `scripts/simulate_api_e2e_replay.py` | Rename `ftmo_enabled_override` key; update endpoint paths |
| `scripts/run_jforex_live.py` | Update any `ftmo_*` CLI arg references |
| `configs/research/governance/ftmo/` | Rename directory to `account_risk/`; rename `ftmo_rules.yaml` to `account_risk_rules.yaml` |
| `Makefile` | Rename `--ftmo-*` flags, `FTMO_*` variables |
| `tests/test_account_risk.py` | Update method calls, field names, config path |
| `tests/test_api_server.py` | Update endpoint paths, model names, dict keys |
| `tests/test_duckdb_state.py` | Update method calls, table name references |
| `tests/test_diagnose_live_performance_gap.py` | Rename `ftmo_allocator_events` table in synthetic DB |
| `scripts/diagnose_live_performance_gap.py` | Rename `ftmo_allocator_events` query if present (conditional — grep first) |

---

### Task 1: Merge ftmo.py into account.py and delete ftmo.py

`src/behemoth/risk/account.py` currently re-exports everything from `ftmo.py`. Absorb all of `ftmo.py`'s actual implementation into `account.py`, rename the classes and functions, and delete `ftmo.py`.

**Files:**
- Modify: `src/behemoth/risk/account.py`
- Delete: `src/behemoth/risk/ftmo.py`

The current `ftmo.py` contains (verified):
- Dataclasses: `FtmoBuffers` (line 12), `FtmoCostGate` (line 18), `FtmoAllocator` (line 30), `FtmoProfile` (line 41)
- Functions: `_to_utc`, `_normalize_trade_cost_gate_mode`, `trading_day_id`, `load_ftmo_profile`, `evaluate_account_limits`, `evaluate_trade_guard`

- [ ] **Step 1: Read both files in full**

Read `src/behemoth/risk/ftmo.py` and `src/behemoth/risk/account.py` completely before making any changes.

- [ ] **Step 2: Rewrite account.py**

Replace the entire content of `account.py` with the full implementation from `ftmo.py`, applying these renames throughout:

| Old | New |
|-----|-----|
| `FtmoBuffers` | `AccountRiskBuffers` |
| `FtmoCostGate` | `AccountRiskCostGate` |
| `FtmoAllocator` | `AccountRiskAllocator` |
| `FtmoProfile` | `AccountRiskProfile` |
| `load_ftmo_profile` | `load_account_risk_profile` |
| `evaluate_account_limits` | `evaluate_account_risk_limits` |

Keep `evaluate_trade_guard`, `trading_day_id`, `_to_utc`, `_normalize_trade_cost_gate_mode` with their existing names (they are already correctly named or internal).

Keep `evaluate_trade_risk_guard` as the public wrapper name (it already exists in account.py under that name — just update it to call the renamed internal function).

The module docstring should read:
```python
"""Broker-neutral account risk management: limits evaluation, trade guard, and allocator."""
```

Do NOT add any `from src.behemoth.risk.ftmo import ...` lines — the goal is to eliminate that dependency entirely.

- [ ] **Step 3: Delete ftmo.py**

```bash
rm src/behemoth/risk/ftmo.py
```

- [ ] **Step 4: Run the account risk tests**

```bash
uv run pytest tests/test_account_risk.py -x -q 2>&1 | tail -10
```

Expected: PASS (or failures that reveal import issues — fix those before proceeding).

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/risk/account.py src/behemoth/risk/ftmo.py
git commit -m "refactor: merge ftmo.py into account.py, rename Ftmo* classes to AccountRisk*"
```

---

### Task 2: Rename FtmoAccountSnapshotRequest in schemas.py

**Files:**
- Modify: `src/behemoth/core/schemas.py`

- [ ] **Step 1: Read the relevant section**

Read `src/behemoth/core/schemas.py` around line 304 to see the full class definition and any usages.

- [ ] **Step 2: Rename the class**

Find:
```python
class FtmoAccountSnapshotRequest(AccountRiskSnapshotRequest):
```

Replace with:
```python
class AccountRiskSnapshotRequest(BaseModel):
```

Wait — the spec says `FtmoAccountSnapshotRequest` should be renamed to `AccountRiskSnapshotRequest`. But `AccountRiskSnapshotRequest` may already exist in schemas.py as the parent class. Read the file carefully to understand the full picture before editing.

If `AccountRiskSnapshotRequest` already exists and `FtmoAccountSnapshotRequest` subclasses it (adding nothing), delete `FtmoAccountSnapshotRequest` entirely and update any references to it elsewhere to use `AccountRiskSnapshotRequest` directly.

If `FtmoAccountSnapshotRequest` is the only definition, rename it to `AccountRiskSnapshotRequest`.

- [ ] **Step 3: Search for all usages of FtmoAccountSnapshotRequest**

```bash
grep -r "FtmoAccountSnapshotRequest" src/ tests/ scripts/ --include="*.py" -n
```

Update each usage to `AccountRiskSnapshotRequest`.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/ -x -q -k "not test_diagnose" 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/core/schemas.py
git commit -m "refactor: rename FtmoAccountSnapshotRequest to AccountRiskSnapshotRequest"
```

---

### Task 3: Rename DB tables and methods in state.py

**Files:**
- Modify: `src/behemoth/runtime/state.py`

This is the most mechanical task. Three DB table names change, all inline SQL referencing them must change, and ten method names change.

- [ ] **Step 1: Read state.py to understand scope**

Read `src/behemoth/runtime/state.py`. Note the `CREATE TABLE` definitions for the three ftmo tables, all INSERT/SELECT/UPDATE SQL strings using those table names, and the ten method names listed below.

- [ ] **Step 2: Rename DB tables in CREATE TABLE statements and all SQL strings**

| Old table name | New table name |
|----------------|----------------|
| `ftmo_account_snapshots` | `account_risk_snapshots` |
| `ftmo_risk_reservations` | `account_risk_reservations` |
| `ftmo_allocator_events` | `account_risk_allocator_events` |

This must be applied to every string in the file that references these table names: `CREATE TABLE`, `INSERT INTO`, `FROM`, `UPDATE`, `SELECT ... FROM`, `JOIN`, `DROP TABLE IF EXISTS`, etc.

Use a global search across state.py:
```bash
grep -n "ftmo_account_snapshots\|ftmo_risk_reservations\|ftmo_allocator_events" \
  src/behemoth/runtime/state.py
```

Edit every matching line.

- [ ] **Step 3: Rename the ten methods**

| Old name | New name |
|----------|----------|
| `record_ftmo_account_snapshot` | `record_account_risk_snapshot` |
| `get_latest_ftmo_account_snapshot` | `get_latest_account_risk_snapshot` |
| `get_ftmo_snapshots_since` | `get_account_risk_snapshots_since` |
| `create_ftmo_risk_reservation` | `create_account_risk_reservation` |
| `promote_ftmo_risk_reservation` | `promote_account_risk_reservation` |
| `release_ftmo_risk_reservation` | `release_account_risk_reservation` |
| `expire_stale_ftmo_pending_reservations` | `expire_stale_account_risk_pending_reservations` |
| `sum_active_ftmo_reserved_loss_ccy` | `sum_active_account_risk_reserved_loss_ccy` |
| `list_active_ftmo_risk_reservations` | `list_active_account_risk_reservations` |
| `log_ftmo_allocator_event` | `log_account_risk_allocator_event` |

- [ ] **Step 4: Verify no ftmo references remain in state.py**

```bash
grep -n "ftmo" src/behemoth/runtime/state.py
```

Expected: no matches.

- [ ] **Step 5: Update test_duckdb_state.py in the same pass**

Before committing, open `tests/test_duckdb_state.py` and apply the same rename map — method call names and any hardcoded table name strings. This keeps pytest green at commit time. See Task 9a for full details; do that sub-task now rather than waiting.

- [ ] **Step 6: Run the state tests**

```bash
uv run pytest tests/test_duckdb_state.py -x -q 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 7: Commit state.py and test_duckdb_state.py together**

```bash
git add src/behemoth/runtime/state.py tests/test_duckdb_state.py
git commit -m "refactor: rename ftmo_* DB tables and state.py methods to account_risk_*"
```

---

### Task 4: Update server.py

This is the largest single-file change. Seven AppConfig fields, two module-level variables/helpers, four Pydantic models, five endpoints, eight risk_metrics_snapshot dict keys, one PredictRequest field, and five Prometheus metrics.

**Files:**
- Modify: `src/behemoth/api/server.py`

- [ ] **Step 1: Read server.py in full before editing**

Read `src/behemoth/api/server.py` completely to understand all locations.

- [ ] **Step 2: Rename AppConfig fields**

| Old | New |
|-----|-----|
| `ftmo_enabled` | `account_risk_enabled` |
| `ftmo_rules_path` | `account_risk_rules_path` |
| `ftmo_profile_id` | `account_risk_profile_id` |
| `ftmo_trade_cost_gate_mode` | `account_risk_trade_cost_gate_mode` |
| `ftmo_enforce_blocks` | `account_risk_enforce_blocks` |
| `ftmo_pending_reservation_ttl_sec` | `account_risk_pending_reservation_ttl_sec` |
| `ftmo_fx_rate_max_age_sec` | `account_risk_fx_rate_max_age_sec` |

Update the field definitions and every reference to them within server.py (lookups via `config.ftmo_*` or `_config.ftmo_*`).

Also update the `BEHEMOTH_` env var prefix strings — e.g. if the field had `env="BEHEMOTH_FTMO_ENABLED"`, it should become `env="BEHEMOTH_ACCOUNT_RISK_ENABLED"`.

Also update the default path: `configs/research/governance/ftmo/ftmo_rules.yaml` → `configs/research/governance/account_risk/account_risk_rules.yaml`.

- [ ] **Step 3: Rename module-level variables and helpers**

| Old | New |
|-----|-----|
| `_ftmo_profile` | `_account_risk_profile` |
| `load_ftmo_profile` alias | Remove — call `load_account_risk_profile` directly |
| `_resolve_ftmo_account_eval()` | `_resolve_account_risk_eval()` |

- [ ] **Step 4: Rename Pydantic models**

| Old | New |
|-----|-----|
| `FtmoLimitsResponse` | `AccountRiskLimitsResponse` |
| `FtmoStatusResponse` | `AccountRiskStatusResponse` |
| `FtmoReservationsStatusResponse` | `AccountRiskReservationsStatusResponse` |
| `FtmoReservationReleaseRequest` | `AccountRiskReservationReleaseRequest` |

- [ ] **Step 5: Rename endpoints**

| Old | New |
|-----|-----|
| `POST /risk/ftmo/snapshot` | `POST /risk/account_risk/snapshot` |
| `GET /risk/ftmo/limits` | `GET /risk/account_risk/limits` |
| `GET /risk/ftmo/status` | `GET /risk/account_risk/status` |
| `GET /risk/ftmo/reservations/status` | `GET /risk/account_risk/reservations/status` |
| `POST /risk/ftmo/reservations/release` | `POST /risk/account_risk/reservations/release` |

- [ ] **Step 6: Rename risk_metrics_snapshot dict keys**

Inside `_build_predictions` (or wherever `risk_metrics_snapshot` dict is constructed):

| Old key | New key |
|---------|---------|
| `ftmo_enabled` | `account_risk_enabled` |
| `ftmo_enabled_effective` | `account_risk_enabled_effective` |
| `ftmo_enabled_override` | `account_risk_enabled_override` |
| `ftmo_mode_source` | `account_risk_mode_source` |
| `ftmo_allow_trading` | `account_risk_allow_trading` |
| `ftmo_account_block_reason` | `account_risk_account_block_reason` |
| `ftmo_profile_id` | `account_risk_profile_id` |
| `ftmo_trade_cost_gate_mode` | `account_risk_trade_cost_gate_mode` |

- [ ] **Step 7: Rename PredictRequest field**

| Old | New |
|-----|-----|
| `ftmo_enabled_override` | `account_risk_enabled_override` |

- [ ] **Step 8: Rename Prometheus metrics**

| Old | New |
|-----|-----|
| `behemoth_ftmo_daily_loss_headroom` | `behemoth_account_risk_daily_loss_headroom` |
| `behemoth_ftmo_max_loss_headroom` | `behemoth_account_risk_max_loss_headroom` |
| `behemoth_ftmo_reserved_loss_ccy` | `behemoth_account_risk_reserved_loss_ccy` |
| `behemoth_ftmo_allocator_blocks_total` | `behemoth_account_risk_allocator_blocks_total` |
| `behemoth_ftmo_allocator_admitted_total` | `behemoth_account_risk_allocator_admitted_total` |

- [ ] **Step 9: Update state method calls in server.py**

server.py calls the state methods renamed in Task 3. Update all calls:
- `_state.record_ftmo_account_snapshot(...)` → `_state.record_account_risk_snapshot(...)`
- `_state.create_ftmo_risk_reservation(...)` → `_state.create_account_risk_reservation(...)`
- etc. (search for any remaining `ftmo` references)

```bash
grep -n "ftmo" src/behemoth/api/server.py
```

Fix every remaining match.

- [ ] **Step 10: Run the API server tests (expect failures — tests are updated in Task 9)**

```bash
uv run pytest tests/test_api_server.py -x -q 2>&1 | tail -10
```

Note the failures — these are expected until tests are updated.

- [ ] **Step 11: Commit**

```bash
git add src/behemoth/api/server.py
git commit -m "refactor: rename ftmo_* to account_risk_* in server.py (config, models, endpoints, metrics)"
```

---

### Task 5: Rewrite scripts — build_account_risk_monitoring_report.py and reconcile_account_risk_reservations.py

Currently these are thin shims that delegate to the ftmo scripts. Absorb the full logic from the ftmo scripts, rename all identifiers, and delete the old scripts.

**Files:**
- Rewrite: `scripts/build_account_risk_monitoring_report.py`
- Rewrite: `scripts/reconcile_account_risk_reservations.py`
- Delete: `scripts/build_ftmo_allocator_monitoring_report.py`
- Delete: `scripts/reconcile_ftmo_reservations.py`

- [ ] **Step 1: Read the ftmo source scripts in full**

Read `scripts/build_ftmo_allocator_monitoring_report.py` and `scripts/reconcile_ftmo_reservations.py` completely to understand the full implementation.

- [ ] **Step 2: Rewrite build_account_risk_monitoring_report.py**

Replace the entire file with the full content of `build_ftmo_allocator_monitoring_report.py`, applying these renames throughout:

- Table name: `ftmo_allocator_events` → `account_risk_allocator_events`
- Metric IDs: `FTMO_ALLOC_*` → `ACCOUNT_RISK_ALLOC_*`
- Module docstring: replace "FTMO" with "account risk"
- Any variable names containing `ftmo` → `account_risk`
- Remove the `from build_ftmo_allocator_monitoring_report import *` shim line

- [ ] **Step 3: Rewrite reconcile_account_risk_reservations.py**

Replace the entire file with the full content of `reconcile_ftmo_reservations.py`, applying these renames throughout:

- Table names: `ftmo_risk_reservations` → `account_risk_reservations`, `ftmo_allocator_events` → `account_risk_allocator_events`
- Module docstring: replace "FTMO" with "account risk"
- Any variable/function names containing `ftmo` → `account_risk`
- Remove the `from scripts.reconcile_ftmo_reservations import *` shim line

- [ ] **Step 4: Delete the old ftmo scripts**

```bash
rm scripts/build_ftmo_allocator_monitoring_report.py
rm scripts/reconcile_ftmo_reservations.py
```

- [ ] **Step 5: Verify no import errors**

```bash
uv run python -c "import scripts.build_account_risk_monitoring_report" 2>&1
uv run python -c "import scripts.reconcile_account_risk_reservations" 2>&1
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: convert account_risk monitoring scripts from shims to standalone implementations"
```

---

### Task 6: Update live scripts (inject_live_observability_data.py, simulate_api_e2e_replay.py, run_jforex_live.py)

These scripts contain `ftmo_*` references that must be renamed.

**Files:**
- Modify: `scripts/inject_live_observability_data.py` (line 39)
- Modify: `scripts/simulate_api_e2e_replay.py` (line 189)
- Modify: `scripts/run_jforex_live.py` (check for `ftmo_*` CLI arg references)

- [ ] **Step 1: Update inject_live_observability_data.py**

Find (line ~39):
```python
"ftmo_enabled_override": True,
```

Replace with:
```python
"account_risk_enabled_override": True,
```

- [ ] **Step 2: Update simulate_api_e2e_replay.py**

Find (line ~189):
```python
"ftmo_enabled_override": True,
```

Replace with:
```python
"account_risk_enabled_override": True,
```

Also scan both files for any `/risk/ftmo/` endpoint paths and update them to `/risk/account_risk/`.

- [ ] **Step 3: Update run_jforex_live.py**

```bash
grep -n "ftmo" scripts/run_jforex_live.py
```

Update any matches — CLI arg names passed to the server (e.g., `--ftmo-enabled-override` → `--account-risk-enabled-override`), dict keys, or variable names. If the grep returns no matches, this file requires no changes.

- [ ] **Step 4: Verify no remaining ftmo references in these scripts**

```bash
grep -n "ftmo" scripts/inject_live_observability_data.py \
  scripts/simulate_api_e2e_replay.py scripts/run_jforex_live.py
```

Expected: no matches.

- [ ] **Step 5: Commit**

```bash
git add scripts/inject_live_observability_data.py scripts/simulate_api_e2e_replay.py scripts/run_jforex_live.py
git commit -m "refactor: rename ftmo_* references in live scripts to account_risk_*"
```

---

### Task 7: Rename configs/research/governance/ftmo/ directory

**Files:**
- Rename: `configs/research/governance/ftmo/` → `configs/research/governance/account_risk/`
- Rename: `ftmo_rules.yaml` → `account_risk_rules.yaml`

- [ ] **Step 1: Rename the directory and file**

```bash
mv configs/research/governance/ftmo configs/research/governance/account_risk
mv configs/research/governance/account_risk/ftmo_rules.yaml \
   configs/research/governance/account_risk/account_risk_rules.yaml
```

- [ ] **Step 2: Check the content of the renamed yaml file**

Open `configs/research/governance/account_risk/account_risk_rules.yaml` and check if it contains any `ftmo_*` keys that should be renamed. If the profile IDs like `ftmo_10k_challenge_2step` are present, leave them as-is (they are user-visible profile identifiers, not code).

- [ ] **Step 3: Verify the default path in server.py and tests points to the new location**

```bash
grep -rn "governance/ftmo\|ftmo_rules.yaml" src/ tests/ scripts/ Makefile --include="*.py"
grep -n "governance/ftmo\|ftmo_rules.yaml" Makefile
```

Fix any remaining hardcoded old paths (these should already be updated from Task 4 — verify here).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: rename governance/ftmo/ config directory to account_risk/"
```

---

### Task 8: Update Makefile flags

Rename `--ftmo-*` CLI flags and `FTMO_*` Makefile variables. The targets that use these flags are the ones that remain after Sub-project A (e.g., `jforex-live`, `ctrader-debug-up` is already deleted).

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Find all remaining ftmo references in Makefile**

```bash
grep -n "ftmo\|FTMO" Makefile
```

Expected locations (lines ~451–455, 488–493, and any remaining variable blocks).

- [ ] **Step 2: Rename variables and flags**

| Old | New |
|-----|-----|
| `FTMO_ENABLED_OVERRIDE` | `ACCOUNT_RISK_ENABLED_OVERRIDE` |
| `FTMO_RULES_PATH` | `ACCOUNT_RISK_RULES_PATH` |
| `FTMO_PROFILE_ID` | `ACCOUNT_RISK_PROFILE_ID` |
| `FTMO_PHASE_MODE` | `ACCOUNT_RISK_PHASE_MODE` |
| `FTMO_ECONOMICS_MODE` | `ACCOUNT_RISK_ECONOMICS_MODE` |
| `FTMO_TRADE_COST_GATE_MODE` | `ACCOUNT_RISK_TRADE_COST_GATE_MODE` |
| `--ftmo-enabled-override` | `--account-risk-enabled-override` |
| `--ftmo-rules-path` | `--account-risk-rules-path` |
| `--ftmo-profile-id` | `--account-risk-profile-id` |
| `--ftmo-phase-mode` | `--account-risk-phase-mode` |
| `--ftmo-economics-mode` | `--account-risk-economics-mode` |
| `--ftmo-trade-cost-gate-mode` | `--account-risk-trade-cost-gate-mode` |

Also update the default path values inside `$(or ...)` expressions:
- `configs/research/governance/ftmo/ftmo_rules.yaml` → `configs/research/governance/account_risk/account_risk_rules.yaml`
- `ftmo_10k_challenge_2step` → leave as-is (profile ID in the yaml, not a code identifier)

- [ ] **Step 3: Verify no ftmo references remain in Makefile**

```bash
grep -n "ftmo\|FTMO" Makefile
```

Expected: no matches (or only inside comments — check each carefully).

- [ ] **Step 4: Verify Makefile still works**

```bash
make help 2>&1 | head -30
```

- [ ] **Step 5: Commit**

```bash
git add Makefile
git commit -m "refactor: rename --ftmo-* flags and FTMO_* variables in Makefile to account_risk_*"
```

---

### Task 9: Update all tests

Four test files need updates. Do them in order: state tests first (unblock test_duckdb_state.py), then the others.

**Files:**
- Modify: `tests/test_duckdb_state.py`
- Modify: `tests/test_account_risk.py`
- Modify: `tests/test_api_server.py`
- Modify: `tests/test_diagnose_live_performance_gap.py`

#### 9a: test_duckdb_state.py

> **Note:** This sub-task was folded into Task 3 (committed together with state.py to keep pytest green). If it was completed there, skip this sub-task. If it was deferred, complete it now.

- [ ] **Step 1: Verify test_duckdb_state.py is already updated**

```bash
grep -n "ftmo" tests/test_duckdb_state.py
```

If no matches: already done, skip to 9b.

- [ ] **Step 2: If matches remain, rename method calls and table references**

Apply the same method rename map from Task 3. Also rename any hardcoded table name strings (`"ftmo_account_snapshots"` etc.) to the new names.

- [ ] **Step 3: Run**

```bash
uv run pytest tests/test_duckdb_state.py -x -q 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 4: Commit if changes were made**

```bash
git add tests/test_duckdb_state.py
git commit -m "test: update test_duckdb_state.py for account_risk_* method and table renames"
```

#### 9b: test_account_risk.py

- [ ] **Step 1: Read test_account_risk.py**

Find all `ftmo_*` references: the config path (`configs/research/governance/ftmo/ftmo_rules.yaml`), any `FtmoProfile`/`FtmoBuffers` class names, any `load_ftmo_profile` calls, any state method calls.

- [ ] **Step 2: Apply renames**

- Config path: `configs/research/governance/ftmo/ftmo_rules.yaml` → `configs/research/governance/account_risk/account_risk_rules.yaml`
- Class names: `FtmoProfile` → `AccountRiskProfile`, etc.
- Function: `load_ftmo_profile` → `load_account_risk_profile`
- State method calls: as per Task 3 map

- [ ] **Step 3: Run**

```bash
uv run pytest tests/test_account_risk.py -x -q 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_account_risk.py
git commit -m "test: update test_account_risk.py for account_risk_* renames and new config path"
```

#### 9c: test_api_server.py

- [ ] **Step 1: Read test_api_server.py**

Find all `/risk/ftmo/` endpoint paths, `FtmoLimitsResponse` etc. model names, `ftmo_enabled_override` field references, and `risk_metrics_snapshot` dict key assertions.

- [ ] **Step 2: Apply renames**

- Endpoint paths: `/risk/ftmo/*` → `/risk/account_risk/*`
- Model names: `FtmoLimitsResponse` → `AccountRiskLimitsResponse`, etc.
- PredictRequest field: `ftmo_enabled_override` → `account_risk_enabled_override`
- Dict keys in snapshot assertions: `ftmo_enabled` → `account_risk_enabled`, etc.

- [ ] **Step 3: Run**

```bash
uv run pytest tests/test_api_server.py -x -q 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_api_server.py
git commit -m "test: update test_api_server.py for account_risk_* endpoint and model renames"
```

#### 9d: test_diagnose_live_performance_gap.py (and its script)

> **Scope note:** `test_diagnose_live_performance_gap.py` was not in the spec's Files Changed table, but it creates a `ftmo_allocator_events` table in its synthetic DB fixture (line 52) and the test subject script may query that same table name. If the table name isn't updated, the test will fail after state.py renames the table. This is an implicit dependency — treat it as in-scope.

- [ ] **Step 1: Read test_diagnose_live_performance_gap.py**

The synthetic DB creation function `_make_synthetic_db` creates `ftmo_allocator_events` table (line 52). This must be renamed.

- [ ] **Step 2: Rename the table in the synthetic DB fixture**

Find:
```python
CREATE TABLE ftmo_allocator_events (
```

Replace with:
```python
CREATE TABLE account_risk_allocator_events (
```

- [ ] **Step 3: Check if scripts/diagnose_live_performance_gap.py queries the old table name**

```bash
grep -n "ftmo" scripts/diagnose_live_performance_gap.py
```

If matches are found, update them. If no matches, no change needed to the script.

- [ ] **Step 4: Run**

```bash
uv run pytest tests/test_diagnose_live_performance_gap.py -x -q 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_diagnose_live_performance_gap.py
# Include scripts/diagnose_live_performance_gap.py only if it had changes
git commit -m "test: rename ftmo_allocator_events to account_risk_allocator_events in diagnostic test"
```

---

### Task 10: Final sweep and verification

- [ ] **Step 1: Run full pytest suite**

```bash
uv run pytest tests/ -q 2>&1 | tail -10
```

Expected: all tests pass, same count as before Sub-project B began.

- [ ] **Step 2: Verify no ftmo references remain in src/ or tests/**

```bash
grep -rn "ftmo\|FTMO" src/ tests/ scripts/ configs/ Makefile \
  --include="*.py" --include="*.yaml" --include="*.json" \
  --exclude-dir=".git"
```

Review every match. Expected survivors:
- Comments or docstrings explaining the rename history (acceptable)
- Profile IDs like `ftmo_10k_challenge_2step` inside `account_risk_rules.yaml` (out of scope per spec)
- `scripts/build_oco_system_reference_docs.py` — internal variable names (out of scope per spec)

Any match in `src/` or `tests/` that is a live code identifier (not a comment) must be fixed.

- [ ] **Step 3: Final commit if cleanup needed**

```bash
git add -A
git commit -m "refactor: clean up remaining ftmo stray references"
```

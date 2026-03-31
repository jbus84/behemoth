# Offline Threshold Seed

## Context

The `/state/seed_audit_history` endpoint replays 20 days of Dukascopy tick parquets through the CatBoost model to populate `audit_logs` with prediction probabilities. The rolling q90 threshold (`get_rolling_threshold()`) needs this history to return a calibrated value on the first live predict call.

The problem: this endpoint runs synchronously inside the API process for 10+ minutes, blocking all other requests. When `run_jforex_live.py` starts the JForex adapter while the API is still seeding, `feed_status` calls timeout (599) and the strategy crashes.

## Goal

Move the seed computation out of the API into a standalone CLI script that runs before the API starts. The API loads pre-computed seed files on startup and remains responsive from the moment it starts serving.

## Non-Goals

- Changing the rolling threshold algorithm or window size
- Parallelizing the seed across symbols (sequential is fine for an offline script)
- Removing the existing `/state/seed_audit_history` endpoint (keep for backward compatibility)
- Phase 1 train prediction seeding (separate concern, not needed for rolling threshold)

## Design

### Standalone CLI: `scripts/seed_rolling_threshold.py`

Runs before the API starts. For each symbol with a governance model binding:

1. **Freshness check:** Read the existing seed file at `data/runtime/seed/{SYMBOL}_threshold_seed.parquet`. If it exists and `max(close_ts) >= today_utc - 1 day`, skip this symbol (already fresh).

2. **Load ticks:** Read Dukascopy tick parquets from `{dukascopy_ticks_dir}/{SYMBOL}/{SYMBOL}_YYYYMM_ticks.parquet` covering the last 20 days.

3. **Aggregate bars:** Convert ticks to `IncomingTick` objects, feed through `TickAggregator(bar_ticks=N)` to produce bars.

4. **Compute features and run inference:** For each candidate, call `compute_feature_matrix_from_bars()`, then `model.predict_proba(X)` to get `pred_prob` values.

5. **Write seed parquet:** Write one parquet file per symbol to `data/runtime/seed/{SYMBOL}_threshold_seed.parquet` with the `audit_logs` schema.

**CLI arguments:**
- `--symbols` (optional, defaults to all symbols with model bindings)
- `--governance-dir` (default: `configs/research/governance/oco`)
- `--models-dir` (default: `models/oco`)
- `--ticks-dir` (default: from `BEHEMOTH_DUKASCOPY_TICKS_DIR`)
- `--seed-dir` (default: `data/runtime/seed`)
- `--days-back` (default: 20)

**Exit codes:** 0 if all symbols seeded or skipped. Non-zero if any symbol with a model binding failed to seed.

### Seed Parquet Schema

Mirrors the `audit_logs` table:

| Column | Type | Description |
|--------|------|-------------|
| `close_ts` | `datetime64[ns, UTC]` | Bar close timestamp |
| `symbol` | `str` | e.g. `GBPUSD` |
| `candidate_uid` | `str` | e.g. `oco\|GBPUSD\|100\|h300\|state_id` |
| `pred_prob` | `float64` | Model prediction probability |
| `threshold` | `float64` | Static threshold from lock |
| `features_json` | `str` | Serialized `ModelFeatures` |
| `model_month` | `str` | e.g. `2026-02` |
| `run_id` | `str` | `threshold_seed` |

### API Startup: Load Seed Files

In `server.py` `lifespan()`, after the state manager is initialized but before `_lifespan_ready = True`:

1. Glob `data/runtime/seed/*_threshold_seed.parquet` (or path from `BEHEMOTH_SEED_DIR` env var).
2. For each file, read the parquet into a DataFrame.
3. Convert rows to the tuple format expected by `_state.log_audit_event_batch()`.
4. Insert into `audit_logs`.

This is fast (parquet read + bulk insert, no model inference) — should take seconds, not minutes.

### Changes to `run_jforex_live.py`

Replace the `_seed_audit_history()` HTTP POST call with a subprocess call to `scripts/seed_rolling_threshold.py` that runs **before** starting the API:

```
1. Run seed_rolling_threshold.py (offline, before API)
2. Start API process
3. _poll_health() → wait for /health 200
4. _warmup_symbols() → fill gap from seed to now
5. Start JForex runner
```

The seed script writes parquets. The API loads them on startup. No blocking HTTP call needed.

### Safety Gate

The API already refuses to trade when `get_rolling_threshold()` returns `None` (insufficient history). A symbol without a seed file simply won't have threshold history, so it won't trade. No additional gating logic is needed.

## Test

Add a test that:
1. Creates a temporary seed parquet with known `pred_prob` values
2. Starts the API (TestClient triggers lifespan)
3. Verifies `get_rolling_threshold()` returns the expected quantile from the seeded data

## Impact

- The API starts and becomes responsive in seconds instead of 10+ minutes
- The JForex adapter can connect immediately after API health check passes
- Per-symbol freshness checks avoid redundant recomputation
- Seed files are inspectable artifacts that can be regenerated independently
- No breaking changes — the existing `/state/seed_audit_history` endpoint remains available

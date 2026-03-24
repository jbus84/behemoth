# Audit Log History Seed — Design Spec

**Date:** 2026-03-24
**Status:** Approved

---

## Problem

The OCO strategy uses a rolling 90th-percentile threshold computed from `audit_logs.pred_prob` over the last 20 days (`rolling_threshold_days=20`, `rolling_threshold_min_history=1000`). When the server starts fresh, `audit_logs` is empty. The current `/predict/warmup` endpoint runs inference once on the current bar buffer and writes the same pred_prob for every bar — it does not produce a real 20-day distribution.

The result: `get_rolling_threshold()` returns `None` at startup → `no_valid_threshold` blocks all trading until enough live events accumulate naturally.

---

## Goal

Seed `audit_logs` with ~20 days of real historical pred_probs (from Dukascopy tick parquets) at server startup, so that `get_rolling_threshold()` returns a calibrated rolling threshold on the very first live predict call.

---

## Architecture

### New endpoint: `POST /state/seed_audit_history`

Accepts:
```json
{
  "symbols": ["GBPUSD", "USDJPY"],   // optional — omit for all live symbols
  "days_back": 20,                    // default 20
  "run_id": "audit_seed"             // default "audit_seed"
}
```

Returns 201:
```json
{
  "ok": true,
  "events_by_symbol": {"GBPUSD": 12400, "USDJPY": 11800, ...},
  "total_events": 24200
}
```

### Replay pipeline (per symbol)

1. Locate parquet files in `dukascopy_ticks_dir/{SYMBOL}/` with timestamps overlapping `[now - days_back, now]`
2. Read and concatenate, sort by `timestamp`
3. Create a **fresh in-memory `StateManager`** + **fresh `TickAggregator`** — completely isolated from the live bar buffer
4. Convert each parquet row to `IncomingTick(symbol, timestamp, bid, ask)`
5. Feed ticks through `TickAggregator.add_ticks()` → `IncomingTickBar`
6. For each emitted bar: `replay_state.append_bar(bar)`
7. Once bar count ≥ `full_warmup_bars` (289): call `compute_features()` → model inference → `replay_state.log_audit_event()` with the bar's real historical `close_ts` and `run_id="audit_seed"`
8. Bulk-copy all `audit_logs` rows from the in-memory replay DB into the live `StateManager`'s DB via `INSERT INTO ... SELECT ...` (DuckDB ATTACH)
9. Close and discard the replay `StateManager`

### Why historical `close_ts` matters

`get_rolling_threshold()` filters by `close_ts >= now() - rolling_threshold_days`. Because seeded rows carry real parquet timestamps (e.g. 2026-03-04 through 2026-03-23), the rolling window query finds them correctly and returns a calibrated 90th-percentile threshold on the first live predict call.

### Threshold chain after seeding

```
seed_audit_history  →  audit_logs: 20 days of real pred_probs
                                    ↓
first predict call  →  schedule expired
                    →  get_rolling_threshold() finds seeded rows
                    →  returns p90 of last 20 days
                    →  threshold_source: "rolling_days:rolling_dynamic"
```

---

## Configuration

One new server config field:

| Field | Env var | Default |
|-------|---------|---------|
| `dukascopy_ticks_dir` | `BEHEMOTH_DUKASCOPY_TICKS_DIR` | `/Users/danielfisher/Desktop/dukascopy_ticks` |

No other config changes. `days_back` and `run_id` are request-time parameters.

---

## Files Changed

| File | Change |
|------|--------|
| `src/behemoth/api/server.py` | Add `SeedAuditHistoryRequest` Pydantic model |
| `src/behemoth/api/server.py` | Add `dukascopy_ticks_dir` to server config with env var |
| `src/behemoth/api/server.py` | Add `POST /state/seed_audit_history` endpoint |
| `scripts/run_jforex_live.py` | Add `_seed_audit_history()` helper |
| `scripts/run_jforex_live.py` | Call `_seed_audit_history()` after `_poll_health`, before `_warmup_symbols` |
| `tests/test_api_server.py` | Add `TestSeedAuditHistory` test class |

---

## Startup Sequence (updated)

```
1. uvicorn starts  →  models load, DB opens
2. _poll_health()  →  server ready
3. _seed_audit_history()  →  20 days of pred_probs in audit_logs
4. _warmup_symbols()  →  gap-fill for hours between parquet end and now
5. _start_live_runner()  →  JForex connects, /backfill sends last ~1 day
6. live predict calls  →  rolling_dynamic threshold from step 3+4 data
```

---

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| `_state` is None | 503 |
| `dukascopy_ticks_dir` missing | 422 |
| No parquets found for a symbol | Warning in response body, symbol skipped, others continue |
| Parquet read error for a symbol | Warning in response body, symbol skipped |
| Replay SM always cleaned up | `finally` block closes in-memory SM |

---

## Testing

`TestSeedAuditHistory` in `tests/test_api_server.py`:

1. **`test_seed_returns_201`** — synthetic parquet with 500 ticks; asserts 201, `ok=True`, `audit_events_written` is int ≥ 0 (may be 0 — fewer than 289 warmup bars is valid)
2. **`test_seed_writes_events_when_sufficient_ticks`** — synthetic parquet with 30,000 ticks (> 289 bars); asserts `audit_events_written > 0` and rows appear in `audit_logs`
3. **`test_seed_503_when_state_uninitialized`** — patches `server._state = None`; asserts 503
4. **`test_seed_skips_missing_symbol_gracefully`** — requests a symbol with no parquet directory; asserts 201 with `events_by_symbol` entry = 0

---

## Out of Scope

- Downloading missing parquets (handled separately by `download_tick_vault_data.py` as a pre-step or nightly cron)
- Deduplication of `audit_logs` rows if endpoint is called multiple times (idempotency: safe to call, just appends; rolling quantile is robust to duplicates)
- Per-bar feature replay fidelity: each bar uses features computed from the in-memory replay buffer, which is the same approach as the backtest pipeline

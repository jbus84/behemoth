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
  "events_by_symbol": {"GBPUSD": 12400, "USDJPY": 11800},
  "total_events": 24200
}
```

### Replay pipeline (per symbol)

1. Locate parquet files in `dukascopy_ticks_dir/{SYMBOL}/` with timestamps overlapping `[now - days_back, now]`
2. Read and concatenate, sort by `timestamp`
3. Resolve the live contract via **`_resolve_runtime_contract(sym, ...)`** to get the list of candidates. This ensures the `canonical_uid` written to `audit_logs` uses the identical format as the live predict path: `f"oco|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"`. `get_rolling_threshold()` filters by both `symbol` and `candidate_uid`, so any format mismatch silently produces zero rows.
4. Create a **fresh in-memory `StateManager`** + **fresh `TickAggregator`** — completely isolated from the live bar buffer
5. Convert each parquet row to `IncomingTick(symbol, timestamp, bid, ask)` — `tick_volume` defaults to 1.0 since Dukascopy parquets do not supply it
6. Feed ticks through `TickAggregator.add_ticks()` → `IncomingTickBar`
7. For each emitted bar: `replay_state.append_bar(bar)`
8. Once bar count ≥ `full_warmup_bars` (289): call `replay_state.compute_features()` → model inference → collect `(candidate_uid, pred_prob, threshold, features, model_month, close_ts, run_id)` into a plain Python list
9. **Write to live DB directly:** call `_state.log_audit_event(...)` once per collected row — the live `StateManager`'s connection is the single writer. The replay `StateManager` is used only to accumulate bars and compute features; it never writes to the live DB.
10. Close and discard the replay `StateManager` in a `finally` block

> **Why not DuckDB ATTACH?** The live `StateManager` holds an exclusive file handle on `live_state.db`. Any attempt to ATTACH that file from another connection — including a read-only attach from the in-memory replay DB — raises a `Binder Error: Unique file handle conflict` at runtime. Direct calls to `_state.log_audit_event()` are the correct single-writer pattern.

### Why historical `close_ts` matters

`get_rolling_threshold()` filters by `close_ts >= now() - rolling_threshold_days`. Because seeded rows carry real parquet timestamps (e.g. 2026-03-04 through 2026-03-13), the rolling window query finds them and returns a calibrated threshold.

### Threshold chain after seeding

```
seed_audit_history  →  audit_logs: N days of real pred_probs with historical close_ts
                                    ↓
first predict call  →  schedule expired
                    →  get_rolling_threshold() finds seeded rows
                    →  returns p90 of available window
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
| `scripts/run_jforex_live.py` | Call `_seed_audit_history()` after `_poll_health`, before `_warmup_symbols` (see ordering note below) |
| `tests/test_api_server.py` | Add `TestSeedAuditHistory` test class |

---

## Startup Sequence (updated)

```
1. uvicorn starts           →  models load, DB opens
2. _poll_health()           →  server ready
3. _seed_audit_history()    →  N days of pred_probs in audit_logs (from parquets)
4. time.sleep(30)           →  wait for JForex initial backfill to populate tick_bars
5. _warmup_symbols()        →  gap-fill: scores live tick_bars buffer, fills parquet→now gap
6. _start_live_runner()     →  JForex connects, /backfill sends ticks
7. live predict calls       →  rolling_dynamic threshold from steps 3+5 data
```

> **Ordering note:** The `time.sleep(30)` between `_seed_audit_history()` and `_warmup_symbols()` must be preserved. `_warmup_symbols()` relies on `/backfill` having already populated `tick_bars` in the **live** `StateManager` (JForex sends this). The seed endpoint writes only to `audit_logs` — it does not populate `tick_bars`. Without ticks in the live buffer, `compute_features()` returns `None` and `_warmup_symbols()` writes 0 events (it will retry and warn, but not error). Step 3 must complete before step 6 begins so that seeded rows are in place before the first live predict call.

---

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| `_state` is None | 503 |
| `dukascopy_ticks_dir` missing | 422 |
| No parquets found for a symbol | 0 in `events_by_symbol`, warning logged, other symbols continue |
| Parquet read error for a symbol | 0 in `events_by_symbol`, warning logged, other symbols continue |
| Replay SM always cleaned up | `finally` block closes in-memory SM |

---

## Testing

`TestSeedAuditHistory` in `tests/test_api_server.py`:

1. **`test_seed_returns_201`** — synthetic parquet with 500 ticks; asserts 201, `ok=True`, `total_events` is int ≥ 0 (may be 0 — fewer than 289 warmup bars is valid)
2. **`test_seed_writes_events_when_sufficient_ticks`** — synthetic parquet with 30,000 ticks (> 289 bars); asserts `total_events > 0` and `events_by_symbol["GBPUSD"] > 0`, and rows appear in live `audit_logs`
3. **`test_seed_503_when_state_uninitialized`** — patches `server._state = None`; asserts 503
4. **`test_seed_skips_missing_symbol_gracefully`** — requests a symbol with no parquet directory; asserts 201 with `events_by_symbol` entry = 0

---

## Known Constraints

- **Parquet coverage may be less than `days_back`:** Parquets currently extend to 2026-03-13 (last download: 2026-03-14). With `days_back=20` on 2026-03-24, the actual coverage is ~10 calendar days. This still exceeds `min_history=1000` (10 days × ~600 bars/day = ~6,000 events), so the rolling threshold computes correctly. If the full 20-day distribution is required, run `download_tick_vault_data.py` before starting the server. The `events_by_symbol` count in the response makes coverage observable.

---

## Out of Scope

- Downloading missing parquets (handled separately by `download_tick_vault_data.py`)
- Deduplication if endpoint is called multiple times (safe to call repeatedly; rolling quantile is robust to duplicates)

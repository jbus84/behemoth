# Dukascopy Paper Trading Readiness Design

## Problem

`make jforex-live` currently supervises the Python API and the JForex live runner, but it does not define symbol-level startup readiness. The live session starts ingesting ticks as soon as the API is healthy, with no explicit guarantee that each symbol has:

- enough historical context for full-precision features
- a bridged path from repo-side historical data to near-real-time broker data
- a clear operational state when a symbol is warming, ready, stale, or failed

This is a gap for paper trading on Dukascopy. The repo already treats historical warmup as canonical in the tester and cBot paths via API `/backfill`, and the API requires `289` 100-tick bars before full-precision predictions are available. The live path needs the same readiness discipline, but per symbol and against a moving near-real-time clock.

## Requirements

1. Trading readiness is managed per symbol, not as an all-or-nothing session gate.
2. The authoritative startup warmup source is local Dukascopy parquet.
3. Local parquet warmup alone is not sufficient because it may lag current market time by about 24 hours.
4. After parquet warmup, the live session must bridge each symbol from the parquet tail to near-real-time using broker-side recent history or recent ticks from Dukascopy.
5. A symbol may open new entries only after both conditions are true:
   - the API has enough warmup data for runtime feature computation
   - the latest ingested tick for that symbol is at most 30 seconds old
6. If a symbol later becomes stale (`> 30s` since last ingested tick), the session pauses new entries for that symbol only.
7. Stale-feed handling does not:
   - cancel pending entry orders automatically
   - force-close filled positions automatically
8. If a symbol cannot complete bridge-to-now within a bounded startup timeout, that symbol stays paused, the session continues for other symbols, and the operator gets an explicit alert/status.
9. Symbol readiness and failure state must be visible in machine-readable runtime status, not only in console logs.
10. `run_jforex_live.py` remains a thin process supervisor; broker-history bridging belongs in the JForex live session.

## Selected Approach

Use a Java-owned per-symbol readiness pipeline inside the JForex live session.

Why this approach:

- It keeps broker connectivity, broker history access, live tick receipt, and symbol tradability in one runtime.
- It reuses the existing Python API as the authoritative state and prediction engine via `/backfill`, `/ticks`, and `/predict`.
- It avoids splitting readiness logic between Python orchestration and Java trading code.

Rejected alternatives:

- Python-owned startup warmup: workable for coarse checks, but poor fit for per-symbol bridge-to-now and ongoing stale-feed handling.
- Live-ticks-only warmup: too implicit and too slow to provide deterministic startup safety.

## Architecture

### Ownership

- `scripts/run_jforex_live.py`
  - starts the Python API
  - waits for API health
  - starts the JForex live runner
  - monitors both processes
  - does not manage per-symbol readiness logic
- `JForexLiveRunner` / `BehemothJForexStrategy`
  - subscribe all configured instruments immediately
  - own symbol readiness lifecycle
  - load parquet warmup
  - bridge to near-real-time from Dukascopy broker history
  - decide whether each symbol is tradable for new entries
- Python API
  - remains the authoritative runtime state/feature/prediction store
  - receives warmup ticks through `/backfill`
  - receives live ticks through existing ingest endpoints

### New live-session components

Add a small, focused readiness layer in Java:

- `HistoricalWarmupLoader`
  - reads the local Dukascopy parquet tail for one symbol
  - chooses enough historical ticks to preserve fixed-tick bar phase and exceed warmup minimum
- `BrokerBridgeLoader`
  - requests recent broker-side ticks/history from Dukascopy starting from the parquet tail timestamp
  - advances the symbol to near-real-time
- `SymbolReadinessRegistry`
  - tracks the current readiness state per symbol
  - tracks last ingested tick timestamp, bar count snapshot, startup timeout, and failure reason
- `FreshnessMonitor`
  - evaluates whether a ready symbol has become stale
  - toggles symbols between `READY` and `STALE_PAUSED`

`BehemothStrategyCore` keeps ownership of trading logic, but gains a per-symbol gate for "entries allowed". Symbols may still ingest ticks and maintain lifecycle state while paused for new entries.

### Concrete warmup and bridge policy

Use the same phase-preserving tail rule already used by `ParquetTickLoader` in the local JForex harness.

Per symbol:

- `phase_bar_ticks = 100`
- `warmup_ticks = 30000`
- `lookback_days = 31`
- `bridge_window = 60 minutes`
- `startup_bridge_timeout = 20 minutes`

Tail-selection algorithm:

1. Set `bridge_start_ts` to the timestamp of the first broker-side tick needed after local parquet history.
2. Count local parquet ticks in `[bridge_start_ts - 31 days, bridge_start_ts)`.
3. Compute `keep = 30000 + (pre_count % 100)`.
4. Load the latest `keep` parquet ticks before `bridge_start_ts`.
5. Send those ticks to API `/backfill` in timestamp order.

This preserves the fixed 100-tick bar phase at the handoff point while keeping the live startup rule aligned with the existing local harness.

Bridge algorithm:

1. Obtain `IHistory` from the JForex strategy context.
2. Request ticks with `IHistory.getTicks(Instrument, long from, long to)` in contiguous 60-minute windows.
3. After each window:
   - convert ticks to existing runtime payloads
   - post them immediately to the Python API
   - update readiness status from `/runtime/feed/status`
4. Stop bridging for that symbol as soon as:
   - latest ingested tick is `<= 30s` old, and
   - API warmup is satisfied
5. If the symbol has not satisfied those conditions within 20 minutes of starting bridge, transition it to `ERROR_PAUSED`.

The bridge must stream windows incrementally and must not materialize an entire 24-hour gap in memory at once.

## Symbol Lifecycle

Each symbol moves through an explicit state machine:

- `COLD`
  - subscribed, but no warmup work completed
- `PARQUET_WARMING`
  - local parquet tail is being loaded and sent to API `/backfill`
- `BRIDGING`
  - broker-side recent history/ticks are filling the gap from parquet tail to near-now
- `READY`
  - symbol may open new entries
- `STALE_PAUSED`
  - symbol was ready, but latest ingested tick is now more than 30 seconds old
- `ERROR_PAUSED`
  - warmup or bridge failed, timed out, or could not satisfy readiness checks

Unlock rule for a symbol:

1. API warmup is satisfied for the traded bar size.
2. Latest ingested tick for that symbol is `<= 30s` old.

Ongoing rule for a symbol:

- if freshness remains within SLA, it stays `READY`
- if freshness exceeds SLA, it moves to `STALE_PAUSED`
- if freshness recovers, it moves back to `READY`
- existing positions and pending orders are not force-closed or auto-cancelled solely due to stale-feed transition

## Data Flow

Per symbol startup flow:

1. Subscribe instrument.
2. Load local parquet tail for that symbol.
3. Send warmup ticks to API `/backfill`.
4. Query Dukascopy broker history/ticks from the parquet tail timestamp forward.
5. Send bridge ticks to the API in timestamp order until the symbol reaches near-real-time.
6. Verify readiness:
   - API warmup satisfied
   - latest ingested tick `<= 30s` old
7. Mark symbol `READY`.
8. Continue normal live tick ingestion through existing `onTick()` flow.

During the live session:

- readiness changes do not unsubscribe the symbol
- readiness changes only affect whether new entries are allowed
- order lifecycle handling continues to use the existing JForex strategy/core flow

## Failure Handling

Failure policy is symbol-scoped.

- Missing or unreadable parquet for one symbol does not kill the whole session.
- Bridge failure for one symbol does not kill the whole session.
- A symbol that fails warmup or bridge transitions to `ERROR_PAUSED`.
- A symbol that cannot reach near-real-time within the startup timeout remains `ERROR_PAUSED` and emits an operator-visible alert.
- Other symbols may still reach `READY` and trade.

The live session should distinguish:

- transient stale-feed pause (`STALE_PAUSED`)
- startup/readiness failure (`ERROR_PAUSED`)

This distinction matters because stale-feed pause may recover automatically, while startup failure may require operator action.

## Operator Visibility

Expose runtime symbol status in machine-readable form under `data/analysis/backtest_reconcile/runtime/` and through metrics.

### Runtime status artifact contract

Write a versioned JSON file at:

- `data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json`

Top-level schema:

```json
{
  "schema_version": 1,
  "as_of_utc": "2026-03-22T12:34:56Z",
  "run_id": "jforex_live",
  "session_tradable_symbol_count": 4,
  "session_total_symbol_count": 6,
  "symbols": [
    {
      "symbol": "EURUSD",
      "state": "READY",
      "entries_allowed": true,
      "parquet_tail_ts_utc": "2026-03-21T23:59:59Z",
      "bridge_start_ts_utc": "2026-03-22T00:00:00Z",
      "bridge_last_requested_to_utc": "2026-03-22T12:00:00Z",
      "last_ingested_tick_ts_utc": "2026-03-22T12:34:40Z",
      "staleness_seconds": 16,
      "warmup_bar_count_100": 312,
      "startup_timeout_reached": false,
      "last_failure_reason": "",
      "last_state_transition_utc": "2026-03-22T12:34:41Z"
    }
  ]
}
```

Contract rules:

- `schema_version` is required and increments on breaking schema changes.
- the file is rewritten on every state transition and at least every 5 seconds while the session is running
- writes are atomic: write to a temp file in the same directory, then rename into place
- consumers must treat the file as the latest complete snapshot, not a log stream
- missing file means runtime status is unavailable, not that all symbols are unready

The readiness file complements, not replaces, `/runtime/feed/status`. The Python API feed status remains the source of truth for last ingested tick timestamps and ingest counters; the readiness file adds live-session state that only Java knows.

Per-symbol status should include:

- readiness state
- tradable for new entries (`true`/`false`)
- parquet tail timestamp used
- bridge start timestamp
- bridge end timestamp
- current last ingested tick timestamp
- current staleness seconds
- current warmup bar count snapshot
- startup timeout reached (`true`/`false`)
- last failure reason
- last state transition timestamp

Recommended alerts:

- symbol stuck non-ready beyond startup timeout
- symbol enters `STALE_PAUSED`
- symbol recovers from `STALE_PAUSED` to `READY`
- symbol enters `ERROR_PAUSED`

## Implementation Boundaries

In scope:

- paper-trading startup readiness for Dukascopy JForex live/demo sessions
- local parquet warmup plus broker bridge-to-now
- per-symbol tradability gate for new entries
- freshness-based pause/resume
- runtime status and alert surfaces

Out of scope:

- crash recovery or automatic process restart
- changing research feature warmup thresholds
- forced cancellation of pending orders on stale feed
- forced closing of filled positions on stale feed
- changing the Python API into the owner of broker-history access

## Testing And Verification Expectations

The implementation plan should include:

1. unit coverage for symbol lifecycle transitions
2. unit coverage for readiness gate behavior in `READY`, `STALE_PAUSED`, and `ERROR_PAUSED`
3. unit coverage for broker bridge timeout behavior
4. unit coverage that stale symbols pause new entries only
5. manual verification path against Dukascopy demo credentials
6. operator-visible verification that runtime status clearly shows mixed symbol states in one session

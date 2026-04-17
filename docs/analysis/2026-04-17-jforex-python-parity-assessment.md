# JForex Live vs Python Backtest Parity Assessment

**Date:** 2026-04-17
**Spec:** docs/superpowers/specs/2026-04-17-jforex-python-parity-assessment-design.md
**Replay day:** 2026-04-15
**Replay symbols:** AUDUSD, USDCHF, EURUSD
**Harness symbols:** all 6 live symbols

## Executive summary

_Pending. Populated in Task 25._

## Methodology

Static code audit across:
- Python: `src/behemoth/`, `src/behemoth/runtime/`, `src/behemoth/api/server.py`, research scripts.
- JForex: `src/jforex/src/main/java/com/behemoth/jforex/**`.

Replay evidence: 2026-04-15 × 3 symbols. Side A = Stage 14 JForex tester. Side B = `scripts/verify_oco_tick_exact_shortlist.py`. Diff in `data/analysis/backtest_reconcile/replay_diff/2026-04-15/parity_replay_diff.parquet`.

Tolerances:
- `pred_prob`: ≤1e-6 absolute
- `fill_price`: ≤1 pip, symbol-aware (JPY crosses use 0.01 pip_size, others 0.0001)
- `gross_pips_outcome`: ≤2 pips
- Tick/bar timestamps: exact to the millisecond

## Surfaces — Core trading path

### core.tick_stream_shape

- **layer:** core
- **python_locus:** src/behemoth/runtime/tick_aggregator.py:30-57; src/behemoth/api/server.py:4158-4235 (ingest_ticks_batch); src/behemoth/api/server.py:4140-4155 (single-tick fallback path)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java:114-135 (onTick); src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:92-165 (onTick → flushSymbol → /ticks/batch, single-tick fallback at 421-444)
- **contract:** Every tick observed by the JForex `onTick` callback will arrive at the Python tick aggregator exactly once, in broker-observed order, with a monotonically increasing `client_tick_seq` scoped per symbol. Backtests consume the same canonical tick parquet the Python aggregator produced live.
- **observed_state:** Code: Java batches up to `sessionConfig.tickBatchSize()` ticks per symbol then POSTs `/ticks/batch`; on HTTP 599 timeout it retries up to 2× with 250 ms backoff, then falls back to per-tick `/ticks` ingest (`ingestTicksIndividually`). Python dedupes by `(symbol, client_tick_seq)` and surfaces accepted/dropped counts plus any `completed_bar_ticks`. Backtest path bypasses the HTTP layer and ingests tick parquet directly. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** critical
- **evidence:** _pending Task 10._
- **harness_check:** yes — core.tick_seq_monotonic
- **fix_owner:** future

### core.bar_boundary_alignment

- **layer:** core
- **python_locus:** src/behemoth/runtime/tick_aggregator.py:34-57 (fixed-tick-count bar assembly); src/behemoth/api/server.py:4197-4216 (bar_completed + completed_bar_ticks echoed to JForex)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:113-165 (flushSymbol consumes `response.barCompleted()` + `response.completedBarTicks()`); BehemothJForexStrategy.java:138-155 (onBar → flushSymbol forces remainder drain at bar close)
- **contract:** A bar is closed iff the Python tick aggregator has accumulated exactly `bar_ticks` ticks for the symbol. JForex never decides bar boundaries independently; it only forwards ticks and reacts to the server's `bar_completed` signal. The backtest pipeline runs the identical aggregator over the same tick stream, so both sides split bars on the same tick indices.
- **observed_state:** Code: Python is the single source of truth for bar closure. `TickAggregator.add_ticks` drains full `bar_ticks`-sized chunks; `/ticks/batch` (and `/ticks`) return `bar_completed=True` + `completed_bar_ticks` once the remainder empties across a boundary. Java only triggers `/predict` when that flag fires. `flushSymbol` on `onBar` ensures the batch buffer is drained at each broker bar close so remainder ticks reach Python promptly. Replay evidence: _pending Task 10._
- **divergence:** none
- **severity:** medium
- **evidence:** _pending Task 10._
- **harness_check:** no — bar boundary decision is single-sided in Python; tick-parity check (core.tick_seq_monotonic) protects the inputs.
- **fix_owner:** n/a

### core.bar_completed_tick_ids

- **layer:** core
- **python_locus:** src/behemoth/api/server.py:4199-4216 (batch response aggregates `completed_bar_ticks` from per-tick internal ingest); src/behemoth/api/server.py:2651-2667 (predict filters candidates by `completed_bar_ticks`)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:136-158 (propagates `response.completedBarTicks()` into `triggerPrediction`); BehemothStrategyCore.java:231-244 (completedBarTicks threaded into `PredictRequestPayload`)
- **contract:** The set of `bar_ticks` granularities returned as completed for a given tick must equal the set of granularities that would have closed at the same tick index in an offline tick-bar build over the same parquet. Live `/predict` must only evaluate candidates whose `bar_ticks` is in that set.
- **observed_state:** Code: `/ticks/batch` sums `completed_bar_ticks` across the batch and echoes the list to JForex; JForex forwards that list verbatim into `PredictRequestPayload.completedBarTicks`; the server filters `candidates` to `int(bar_ticks) in completed_ticks`. The offline backtest writes the same flag via the aggregator → `append_bar` flow. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** high
- **evidence:** _pending Task 10._
- **harness_check:** yes — core.predict_cycles_per_bar
- **fix_owner:** future

### core.feature_computation_locus

- **layer:** core
- **python_locus:** src/behemoth/api/server.py:2697-2745 (per-candidate rolling features + regime quantiles computed inside `/predict`); src/behemoth/api/server.py:2860-2945 (`_build_predictions` invokes model on the computed feature vector)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:231-278 (Java only builds `PredictRequestPayload`, never computes features); src/jforex/src/main/java/com/behemoth/jforex/runtime/dto/PredictRequestPayload.java (payload has no feature fields)
- **contract:** All model features are derived from the server-side bar buffer in Python. JForex is a pure forwarder; no feature computation occurs client-side, by design. Any feature-level divergence can therefore only arise from divergent inputs (tick stream or bar set), not from duplicated formulas.
- **observed_state:** Code: `_state.compute_features` + `_state.compute_regime_quantiles` are only invoked inside the `/predict` handler; the Java runtime's DTO carries symbol/volume/completed_bar_ticks/run_id/bar_ordinals and no feature vector. Replay evidence: _pending Task 10._
- **divergence:** none
- **severity:** low
- **evidence:** _pending Task 10._
- **harness_check:** no — single-sided computation; covered indirectly by tick + bar-boundary checks.
- **fix_owner:** n/a

### core.prediction_request_payload

- **layer:** core
- **python_locus:** src/behemoth/api/server.py:2206-2251 (`PredictRequest` schema: symbol, risk_enabled_override/account_risk_enabled_override, requested_volume_units/requested_lot_size, completed_bar_ticks, bar_ordinals, run_id); src/behemoth/api/server.py:2617-2745 (handler reads these fields)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/runtime/dto/PredictRequestPayload.java:6-13 (record fields: symbol, riskEnabledOverride, requestedVolumeUnits, completedBarTicks, runId, barOrdinals); src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:237-244 (payload construction)
- **contract:** The JForex-side `PredictRequestPayload` record serialises one-to-one onto the Python `PredictRequest` alias schema. Field semantics (types, units, nullability, alias casing) must match or the request is rejected / silently coerced.
- **observed_state:** Code: Java sends `{symbol, riskEnabledOverride, requestedVolumeUnits, completedBarTicks, runId, barOrdinals}`; Python accepts those exact aliases via `populate_by_name=True`. Note: Java sends `Map<Integer, Long>` for `barOrdinals` but Python expects `dict[str, int]` — JSON serialisation coerces integer keys to strings, which matches Python's contract; longs beyond JS safe integer are not expected in session-ordinals. `requestedLotSize` and `accountRiskEnabledOverride` are Python-only aliases and are not sent by Java. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** high
- **evidence:** _pending Task 10._
- **harness_check:** no — DTO-schema parity is enforced at deserialisation time; a schema drift test is out-of-scope for the seed-check set.
- **fix_owner:** future

### core.selected_exec_decision

- **layer:** core
- **python_locus:** src/behemoth/api/server.py:2994 (`preselected_exec = 1 if (regime_active and pred_prob >= curr_threshold) else 0`); src/behemoth/api/server.py:3024-3053 (account-risk gate may demote `selected_exec` to 0)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:245-268 (consumes `response.predictions()` and `response.actions()` as-is; no client-side re-evaluation of thresholds or probabilities)
- **contract:** The exec-selection decision is made entirely on the Python side using `regime_active && pred_prob >= curr_threshold`, then demoted if the account-risk trade guard blocks. JForex receives `selected_exec` and acts on the resulting `actions` list without re-checking threshold/regime.
- **observed_state:** Code: Python uses a plain `>=` comparison (no epsilon tolerance) against `curr_threshold` (model-expiry, rolling-gap, and no-rolling-config guards force `curr_threshold = 2.0`, i.e. always-block). Java-side `executeActions` iterates `response.actions()` and does not re-score; the only client-side block is `state.entriesAllowed` (see core.entries_allowed_vs_readiness / lifecycle surfaces). Replay evidence: _pending Task 10._
- **divergence:** none
- **severity:** low
- **evidence:** _pending Task 10._
- **harness_check:** no — the decision is single-sided in Python; `pred_prob` numerical parity is already covered by the ≤1e-6 tolerance in the replay-diff methodology.
- **fix_owner:** n/a

### core.barrier_touch_detection

- **layer:** core
- **python_locus:** src/behemoth/runtime/barrier_manager.py:176-287 (`evaluate_bar` — bar_high_ask vs upper, bar_low_bid vs lower, hl_first tie-break); src/behemoth/api/server.py:2749-2793 (`/predict` calls `evaluate_bar` with the latest bar's high/low/hl_first)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:231-278 (receives `BarrierActionPayload[]` from `/predict` response and executes OPEN_MARKET / CLOSE_MARKET verbatim)
- **contract:** Barrier-touch detection is a Python-only computation driven by the completed bar's `high_bid`, `low_bid`, `high_ask`, and `hl_first`. JForex never evaluates barriers itself. Divergence is only possible through divergence in the inputs (the bar's OHLC/hl_first fields), not through divergent logic.
- **observed_state:** Code: `BarrierManager.evaluate_bar` is invoked inside the `/predict` handler using `_state.get_latest_bar(sym, bt)` (same bar buffer as offline backtest). Returned `OPEN_MARKET` / `CLOSE_MARKET` / `RELEASE_RESERVATION` actions are forwarded through the response; Java iterates and submits/closes orders without additional logic. Replay evidence: _pending Task 10._
- **divergence:** none
- **severity:** medium
- **evidence:** _pending Task 10._
- **harness_check:** no — logic is single-sided; input-parity is covered by bar-alignment + tick-parity checks.
- **fix_owner:** n/a

### core.order_open_market_submit

- **layer:** core
- **python_locus:** src/behemoth/runtime/barrier_manager.py:238-269 (Python emits `OPEN_MARKET` actions with symbol, side, candidate_uid, scan_id, reservation_id, horizon); src/behemoth/api/server.py:2784-2793 (actions packed into `PredictResponse`)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:280-317 (`executeActions` OPEN_MARKET branch: computes `amountMillions = requestedVolumeUnits / 1_000_000`, builds `MarketOrderRequest`, calls `JForexExecutionPort.submitMarketOrder`); src/jforex/src/main/java/com/behemoth/jforex/JForexExecutionPort.java:51-68 (engine.submitOrder with BUY/SELL command and amountMillions)
- **contract:** For every `OPEN_MARKET` action emitted by Python, JForex will submit a broker market order for `requested_volume_units / 1_000_000` FX millions, with label `BM_<scan_id>_<side>`, only when `state.entriesAllowed` is true. The broker fill ACK must then sync back to Python via `/trades/open` (see core.fill_ack_syncs_trade_open).
- **observed_state:** Code: volume sizing divides the Python-requested integer volume units by `FX_UNITS_PER_MILLION = 1_000_000.0`; the JForex `IEngine.submitOrder(label, instrument, BUY|SELL, amountMillions)` overload expects FX millions. `entriesAllowed=false` records `entry_blocked_not_ready` and skips the submit. `scanToOrderLabel[scan_id]=label` is recorded before the submit so later CLOSE_MARKET actions can resolve the broker order. On submit failure `pendingFills` is rolled back. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** critical
- **evidence:** _pending Task 10._
- **harness_check:** yes — core.entries_allowed_vs_readiness
- **fix_owner:** future

### core.order_close_market_submit

- **layer:** core
- **python_locus:** src/behemoth/runtime/barrier_manager.py (CLOSE_MARKET actions emitted from HOLDING→COMPLETED transitions, with `scan_id` and `broker_pos_id`); src/behemoth/api/server.py:2784-2793 (actions packed into `PredictResponse`)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:318-332 (`executeActions` CLOSE_MARKET branch: resolves label via `scanToOrderLabel.remove(action.scanId())` and calls `executionPort.closePosition(symbol, orderLabel)`); src/jforex/src/main/java/com/behemoth/jforex/JForexExecutionPort.java:84-94 (engine.getOrder(label).close())
- **contract:** For every `CLOSE_MARKET` action Python emits, JForex will close exactly the open position whose label was recorded in `scanToOrderLabel` at OPEN_MARKET time. If the label is missing (map eviction, restart without state), the close is skipped and recorded as `barrier_close_skipped_no_label`.
- **observed_state:** Code: close resolution is label-based (not broker_pos_id-based) and the mapping is in-process only — no persistence across JForex restarts, and `scanToOrderLabel.remove` consumes the entry. If Python retries a CLOSE_MARKET after a JForex restart, the label will no longer be resolvable. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** high
- **evidence:** _pending Task 10._
- **harness_check:** yes — lifecycle.active_oco_reconciled
- **fix_owner:** future

### core.fill_ack_syncs_trade_open

- **layer:** core
- **python_locus:** src/behemoth/api/server.py:3358-3407 (`/trades/open` handler: calls `_state.open_trade` with entry_price/entry_ts, promotes risk reservation, binds broker_pos_id onto the matching HOLDING scan via `_barrier_manager.set_broker_pos_id`)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:335-362 (`handleFill`: builds `TradeOpenRequestPayload` with `event.openPrice()` and `fillTs = event.fillTimeUtc()`; falls back to `Instant.now()` if the broker omitted `fillTime`); BehemothJForexStrategy.java:199-226 (toOrderEvent lifts `openPrice` + `fillTime` from the Dukascopy `IOrder`)
- **contract:** After each `ORDER_FILL_OK` from the broker, JForex will POST `/trades/open` with the broker's actual `openPrice` and `fillTs`, the broker `orderId`, the side inferred from the label (`BUY|SELL`), and the original `candidate_uid`/`reservation_id`/`horizon` recovered from `pendingFills[label]`. The Python ledger and barrier manager then reconcile the broker position into the scan.
- **observed_state:** Code: `pendingFills` is keyed by label and removed on first ACK; if ACK is missed the context is lost and trade-open sync proceeds with empty candidate_uid/reservation_id/horizon=0 (logged via `recordTradeSyncFailure`). Side is inferred lexically from `event.orderLabel().contains("BUY")` — this depends on labels always being `BM_<scan>_BUY|SELL`. `fillTs` fallback to `Instant.now()` introduces a small clock-skew risk when the broker omits `fillTime`. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** high
- **evidence:** _pending Task 10._
- **harness_check:** no — sync correctness is observable via `/trades/active` reconciliation (covered by lifecycle.active_oco_reconciled) rather than a dedicated seed check.
- **fix_owner:** future

## Surfaces — Lifecycle & state

### lifecycle.client_tick_seq_monotonic

- **layer:** lifecycle
- **python_locus:** src/behemoth/api/server.py:4016-4046 (`_ingest_tick_internal` — dedupes on equality and rejects regressions via `last_client_tick_seq`); src/behemoth/api/server.py:4100-4102 (advance on accept); src/behemoth/api/server.py:1513-1516 / 2309-2312 (feed tracker defaults + summary schema)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:85-105 (`seedClientTickSeq`, `onTick` increments `state.nextClientTickSeq`); src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:446-457 (`SymbolRuntimeState.nextClientTickSeq` initialised to 1L)
- **contract:** For each symbol, `client_tick_seq` is a strictly increasing per-symbol integer assigned by JForex at `onTick` time. Python will reject any tick whose seq equals the last accepted (`duplicate_client_tick_seq`) or is smaller (`non_monotonic_client_tick_seq`) and will never advance `last_client_tick_seq` backwards.
- **observed_state:** Code: Java `SymbolRuntimeState.nextClientTickSeq` starts at 1L, post-increments on every `onTick` enqueue, and can be re-seeded via `seedClientTickSeq(symbol, lastClientTickSeq)` (used for cross-restart continuation). Python stores `last_client_tick_seq` in the per-symbol feed tracker and advances it only after accept; on equal or lower incoming values the tick is dropped with counters `duplicate_client_tick_seq` / `client_seq_violations`. When `client_tick_seq` is present the timestamp-monotonicity check is demoted to informational (duplicates and regressions counted but not rejected). Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** critical
- **evidence:** _pending Task 10._
- **harness_check:** yes — core.tick_seq_monotonic
- **fix_owner:** future

### lifecycle.reservation_id_lifecycle

- **layer:** lifecycle
- **python_locus:** src/behemoth/runtime/state.py:870-1107 (`create_account_risk_reservation` → `promote_account_risk_reservation` → `release_account_risk_reservation` / `expire_stale_account_risk_pending_reservations`); src/behemoth/runtime/barrier_manager.py:107-123 (reservation_id stored on scan row); src/behemoth/runtime/barrier_manager.py:229-282 (RELEASE_RESERVATION emitted on tie-expiry or scan expiry); src/behemoth/api/server.py:3383-3395 (/trades/open promotes PENDING → OPEN and binds to broker_pos_id)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:297-317 (stores `reservationId` inside `PendingFillContext` keyed by order label); BehemothStrategyCore.java:340-356 (`handleFill` pops the context and forwards `reservation_id` on /trades/open); BehemothStrategyCore.java:466-471 (`PendingFillContext` record)
- **contract:** Every PENDING reservation_id issued at selection must terminate in exactly one of: promoted to OPEN by `/trades/open` (bound to broker_pos_id), released on scan expiry / tie, released on `/trades/update` close, or expired by the stale-PENDING sweep. No PENDING row will leak past the expiry TTL, and every HOLDING scan with a broker fill will have its reservation_id promoted to OPEN within one /trades/open round-trip.
- **observed_state:** Code: Python issues reservation_id inside `/predict` and attaches it to the barrier scan; `OPEN_MARKET` and `RELEASE_RESERVATION` actions carry `reservation_id` to JForex. JForex does not mutate or persist reservation_id — it just threads it through `PendingFillContext` (in-memory only) and replays it back on `/trades/open`. Risk: if JForex restarts between order submit and fill, the in-memory `pendingFills[label]` entry is lost and `/trades/open` will be sent with `reservation_id=""` (see lifecycle.pending_fills_map), leaving the Python PENDING row to be cleaned up by `expire_stale_account_risk_pending_reservations`. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** high
- **evidence:** _pending Task 10._
- **harness_check:** no — reservation-lifecycle correctness spans three endpoints and a stale-sweep timer; covered indirectly by `lifecycle.active_oco_reconciled` (which catches orphan active rows) plus DB-side assertions in `scripts/diagnose_live_audit.py`.
- **fix_owner:** future

### lifecycle.active_oco_state_json

- **layer:** lifecycle
- **python_locus:** src/behemoth/runtime/barrier_manager.py:15-41 (`barrier_scans` table DDL in `live_state.db`); src/behemoth/runtime/barrier_manager.py:125-164 (`reject_legacy_active_scans`, `has_active_scan`, `find_holding_scans`); src/behemoth/runtime/state.py:78-101 (`trades` table DDL, which is the Python side of active-position recovery); src/behemoth/api/server.py:3410-3415 (`/trades/active` reconciliation endpoint)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java:81-82 (`ExecutionStateStore` rooted at `sessionConfig.reportDir().resolve("runtime").resolve("active_oco_state.json")`); src/jforex/src/main/java/com/behemoth/jforex/state/ExecutionStateStore.java:19-132 (load/persist, index by order label, fill/close/cancel state transitions); src/jforex/src/main/java/com/behemoth/jforex/state/OcoGroupState.java:8-82 (group + leg schema with `candidateUid`, `reservationId`, `runId`, `barTicks`, per-leg `status` ∈ {PLANNED, SUBMIT_OK, FILLED, CANCEL_REQUESTED, CANCELLED, CLOSED, REJECTED})
- **contract:** For each active OCO group the JForex-side `active_oco_state.json` and the Python `live_state.db` (barrier_scans + trades) will agree: every group with `buyLeg.isActive()` or `sellLeg.isActive()` in JSON corresponds to either a SCANNING/HOLDING row in `barrier_scans` or an OPEN row in `trades` (by `reservationId`/`candidateUid`/`runId`), and every such Python row has a JSON entry. No one-sided lifecycle states after restart or reconnect.
- **observed_state:** Code: `ExecutionStateStore.persist()` writes after every state transition so the JSON is crash-consistent on the JForex side. Python's barrier_scans survive via `persist_path` (DuckDB). However, there is no dedicated reconciliation loop that diffs the two stores end-to-end on startup — reconciliation relies on per-event replay (/trades/open binding broker_pos_id into the matching HOLDING scan at `find_holding_scans`) and on `/trades/active` being queried by JForex recovery code. Legacy barrier_scans without side-aware `signal_close_ask/bid` are force-expired on Python startup via `reject_legacy_active_scans`. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** high
- **evidence:** _pending Task 10._
- **harness_check:** yes — lifecycle.active_oco_reconciled
- **fix_owner:** future

### lifecycle.barrier_scan_status_transitions

- **layer:** lifecycle
- **python_locus:** src/behemoth/runtime/barrier_manager.py:44-49 (documented SCANNING → HOLDING → COMPLETED / EXPIRED state machine); src/behemoth/runtime/barrier_manager.py:176-326 (`evaluate_bar` + `_transition_to_holding` implement the transitions); src/behemoth/runtime/barrier_manager.py:125-156 (`reject_legacy_active_scans` terminal-transitions stale SCANNING/HOLDING rows on startup)
- **jforex_locus:** _no client-side equivalent — JForex does not own scan state; it only consumes `OPEN_MARKET` / `CLOSE_MARKET` / `RELEASE_RESERVATION` actions emitted by Python._ src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:280-333 (action consumer)
- **contract:** Each barrier scan will follow one of exactly two terminal paths: SCANNING → HOLDING → COMPLETED (emits OPEN_MARKET then CLOSE_MARKET) or SCANNING → EXPIRED (emits RELEASE_RESERVATION if a reservation was attached). A Python restart with a persistent `live_state.db` must not leave a HOLDING scan without continuing its hold_bars_remaining countdown on the next bar — HOLDING scans are the only state that depends on subsequent bar evaluation to progress to CLOSE_MARKET.
- **observed_state:** Code: `evaluate_bar` decrements both `scan_bars_remaining` (SCANNING) and `hold_bars_remaining` (HOLDING) atomically per bar and transitions to EXPIRED / COMPLETED when the counter hits zero. Simultaneous up/down touch with `hl_first == 0` terminates as EXPIRED (mirrors `_oco_precompute`). Ties with a reservation_id emit `RELEASE_RESERVATION` so Python can clean up. Restart risk: on reconnect, HOLDING rows remain in `live_state.db` with their `hold_bars_remaining` frozen at the value before shutdown; they will only resume counting if `/predict` continues to be driven by bar completions for the same symbol/bar_ticks pair — any gap in bar ingestion delays CLOSE_MARKET. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** high
- **evidence:** _pending Task 10._
- **harness_check:** no — the state-machine integrity check is covered by `lifecycle.active_oco_reconciled` at the JSON↔DB boundary; a dedicated per-transition seed check is out of scope.
- **fix_owner:** future

### lifecycle.scan_to_order_label_map

- **layer:** lifecycle
- **python_locus:** _no Python counterpart — Python emits `CLOSE_MARKET` actions with `scan_id` and expects JForex to resolve to an open broker order._ src/behemoth/runtime/barrier_manager.py:298-311 (CLOSE_MARKET emit path); src/behemoth/runtime/barrier_manager.py:328-333 (`set_broker_pos_id` is the only Python-side persisted link)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:45 (`Map<String, String> scanToOrderLabel = new LinkedHashMap<>();`); BehemothStrategyCore.java:296 (put on OPEN_MARKET submit); BehemothStrategyCore.java:319-330 (remove+close on CLOSE_MARKET, else `barrier_close_skipped_no_label`)
- **contract:** For the lifetime of an active barrier scan, JForex will hold a `scan_id → order_label` mapping that CLOSE_MARKET actions use to close the correct broker position. The mapping must survive the full scan lifetime — from OPEN_MARKET submit through the final HOLDING bar.
- **observed_state:** Code: `scanToOrderLabel` is an in-memory `LinkedHashMap` with no persistence; a JForex restart between OPEN_MARKET submit and CLOSE_MARKET emit will empty the map, and Python's CLOSE_MARKET will be dropped as `barrier_close_skipped_no_label`. There is no durable label-lookup fallback (e.g. via `ExecutionStateStore` even though group/leg labels exist there). This is a known recovery gap. Replay evidence: _pending Task 10._
- **divergence:** observed
- **severity:** critical
- **evidence:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:45,296,319-330 (in-memory only, no persistence); _replay evidence pending Task 10._
- **harness_check:** no — JForex-local in-memory map; parity harness has no visibility into this process memory. Observable only indirectly via `barrier_close_skipped_no_label` operational events.
- **fix_owner:** future

### lifecycle.pending_fills_map

- **layer:** lifecycle
- **python_locus:** _no Python counterpart — Python expects `/trades/open` to carry the correct `candidate_uid`, `reservation_id`, and `horizon`._ src/behemoth/api/server.py:3358-3395 (consumer: promotes reservation, binds broker_pos_id, opens trade row)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:43 (`Map<String, PendingFillContext> pendingFills = new LinkedHashMap<>();`); BehemothStrategyCore.java:297-301 (put on OPEN_MARKET submit); BehemothStrategyCore.java:313-314 (rollback on submit failure); BehemothStrategyCore.java:340-356 (remove on `handleFill`, forward ctx to `/trades/open`); BehemothStrategyCore.java:466-471 (`PendingFillContext` record: candidateUid, reservationId, horizon)
- **contract:** For every submitted market order, JForex will retain `(candidateUid, reservationId, horizon)` keyed by order label until the broker ACKs with `ORDER_FILL_OK`, at which point the context will be consumed exactly once and forwarded to Python via `/trades/open`. If the context is missing, `/trades/open` sends empty `candidate_uid`/`reservation_id` and `horizon=0`, leaving the PENDING reservation to be TTL-expired and the trade row missing its entry model context.
- **observed_state:** Code: `pendingFills` is an in-memory `LinkedHashMap`; a restart between submit and fill-ACK loses the context entirely. The sole rollback path (`pendingFills.remove(label)` on submit exception) covers only synchronous submit failures, not disconnect-or-crash scenarios. `handleFill` falls back silently to empty strings + horizon=0, producing `/trades/open` rows that bypass audit_logs linkage (the `open_trade` helper logs a WARN when no matching audit row exists — see state.py:593-596). Known recovery gap. Replay evidence: _pending Task 10._
- **divergence:** observed
- **severity:** critical
- **evidence:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:43,297-301,340-356 (in-memory only); src/behemoth/runtime/state.py:592-597 (silent-fallback warning on missing audit linkage); _replay evidence pending Task 10._
- **harness_check:** no — JForex-local in-memory map; observable only indirectly via trades rows with NULL `entry_pred_prob` / empty `reservation_id` after a restart.
- **fix_owner:** future

### lifecycle.bar_ordinals_by_bar_ticks

- **layer:** lifecycle
- **python_locus:** src/behemoth/api/server.py:2206-2251 (PredictRequest schema — `bar_ordinals: dict[str, int]` alias `barOrdinals`); src/behemoth/api/server.py:2617-2745 (`/predict` handler consumes ordinals for candidate filtering / audit context)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:231-244 (`triggerPrediction` increments `state.barOrdinalsByBarTicks` per completed `bar_ticks` and snapshots the map into `PredictRequestPayload.barOrdinals`); BehemothStrategyCore.java:452 (`Map<Integer, Long> barOrdinalsByBarTicks` on SymbolRuntimeState, seeded empty)
- **contract:** For each `(symbol, bar_ticks)` pair, the ordinal sent on `/predict` will be monotonically non-decreasing across the session (strictly +1 per completed bar), starting at 0 on the first completion and incrementing by 1 on each subsequent bar. Python treats the ordinal as the authoritative session-scoped bar index for that granularity; any repeat or regression indicates a JForex restart or a lost bar-completed signal.
- **observed_state:** Code: Java uses `compute((k,v) -> v == null ? 0L : v + 1L)` — first call stores 0L, so the first prediction for a fresh process carries ordinal 0, second 1, etc. The map is in-memory only, so a JForex restart resets every symbol's counter back to 0 even though Python's bar buffer may be mid-stream; this will create overlapping ordinal ranges if Python compares ordinals across sessions. `Map.copyOf` snapshotting guarantees the request serialises a consistent view. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** high
- **evidence:** _pending Task 10._
- **harness_check:** no — ordinal monotonicity is single-symbol per-session; no seed check exists. Covered indirectly by `core.predict_cycles_per_bar` (one /predict per completed bar) and `time_data.bar_close_ts_sorted_per_symbol` (close_ts ordering on the Python side).
- **fix_owner:** future

## Surfaces — Risk & governance

### risk_gov.volume_sizing_source

- **layer:** risk_gov
- **python_locus:** src/behemoth/api/server.py:1233-1246 (`_resolve_requested_volume_units` — mandates `requested_volume_units > 0` or a positive `requested_lot_size`); src/behemoth/api/server.py:2628,2735,3149-3201 (reservation sizing uses the resolved value); src/behemoth/risk/account.py:159-224 (`evaluate_account_risk_limits` — account-level headroom/limits evaluation feeding the trade guard); src/behemoth/risk/account.py:227-300 (`evaluate_trade_guard` — per-candidate admission given `barrier_pips`/`cost_est_pips` and the resolved account state)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java:13-93 (`requestedVolumeUnits` record field, validated > 0 in the compact constructor); src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:231-244 (passes `sessionConfig.requestedVolumeUnits()` on every `/predict`); src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:280-317 (`executeActions` converts to millions via `sessionConfig.requestedVolumeUnits() / FX_UNITS_PER_MILLION` before `IEngine.submitOrder`)
- **contract:** The requested FX-unit volume Python reserves against the allocator / account-risk headroom via `/predict` will equal the FX-unit volume JForex converts to millions and submits to the broker for the same scan. Session-config drift (a different `BEHEMOTH_JFOREX_REQUESTED_VOLUME_UNITS` than Python reserved against) must be impossible for any single `/predict` → `OPEN_MARKET` → `IEngine.submitOrder` chain.
- **observed_state:** Code: Java sends the same `requestedVolumeUnits` value on every `/predict` for the session (it is read once from `JForexSessionConfig`, a final record); Python's `/predict` both resolves the admission against that value (`_resolve_requested_volume_units`) and uses it to compute reservation currency via `gross_loss_pips * pip_value_per_unit * requested_volume_units`. On OPEN_MARKET, Java divides the same value by `FX_UNITS_PER_MILLION = 1_000_000.0` and submits `amountMillions`. Drift windows: if the JForex process is restarted with a different `BEHEMOTH_JFOREX_REQUESTED_VOLUME_UNITS` mid-session, PENDING reservations issued under the old value will be promoted against the new submit volume (single-session-config invariant not enforced by Python). Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** critical
- **evidence:** _pending Task 10._
- **harness_check:** no — the two-sided volume check compares a Python reservation number to a broker submit amount across a process boundary; no dedicated seed check covers it. Covered indirectly by `lifecycle.active_oco_reconciled` (mismatched volumes surface as reconciliation drift).
- **fix_owner:** future

### risk_gov.governance_lock_model_month

- **layer:** risk_gov
- **python_locus:** src/behemoth/api/server.py:89-97 (`_model_months` cache keyed by `symbol|model_month`); src/behemoth/api/server.py:929-977 (lock binding loader — reads `model_month` from `*_oco_live_lock.json` artifacts and pins it per symbol); src/behemoth/api/server.py:1014,1599-1625,1680 (predict/contract path uses `expected_month = binding.model_month` for audit/context resolution); src/behemoth/api/server.py:377-384,1554-1584 (`BEHEMOTH_FORCE_MODEL_MONTH` override and normalization)
- **jforex_locus:** _no client-side equivalent — JForex never reads or validates `model_month`._ src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java:13-39 (session config carries `runId` but no `model_month` field); src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:231-244 (every `/predict` request ships only `runId`, expecting Python to resolve the model month)
- **contract:** Python is the single authority on `model_month`; it resolves the locked month from the per-symbol governance lock at startup and pins predictions to that month. JForex must pass a `runId` that corresponds to a run whose audit trail lands within the currently locked month — a `runId` belonging to a stale (unlocked) month must not silently produce predictions under a newer model without tripping the governance validator.
- **observed_state:** Code: on `init_models`, Python reads `model_month` from each symbol's `*_oco_live_lock.json` under `artifacts.model_month` and caches it in `_model_months`; `/predict` uses the cache key `f"{symbol}|{model_month}"` with `model_month` resolved from the active binding (not from the request). JForex's `runId` is propagated to audit rows only; there is no server-side assertion that the run's earlier predictions (if any) were made under the same lock generation. `scripts/validate_oco_live_governance.py` asserts `model_month_matches_cbm_name` and `model_month_matches_threshold_json` at deploy/retrain time, but no runtime gate rejects mid-session lock drift. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** critical
- **evidence:** _pending Task 10._
- **harness_check:** yes — risk_gov.governance_lock_pin
- **fix_owner:** future

### risk_gov.governance_lock_hash_integrity

- **layer:** risk_gov
- **python_locus:** scripts/validate_oco_live_governance.py:29-35 (`_sha256` helper); scripts/validate_oco_live_governance.py:93-216 (`run` — per-artifact hash recompute + expected-hash match for `wfo_config`, `reduced_config`, `reduced_states_csv`, `predictions`, `model_cbm`, `model_threshold_json`, `tick_exact_summary`, `reduced_summary`; plus `lock_provenance_clean` on `git.dirty`); configs/research/governance/oco/audusd_oco_live_lock.json:1-23 (lock artifact with `*_sha256` fields for each referenced file)
- **jforex_locus:** _no client-side equivalent — JForex does not read the lock JSON or verify artifact hashes._ src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:231-244 (JForex trusts whatever Python has loaded at session start)
- **contract:** At session-start (deploy mode) and at every retrain boundary, every hash in `*_oco_live_lock.json` (model .cbm, threshold .json, reduced/wfo configs, reduced-states CSV, predictions parquet, tick-exact summary) must match the current file contents on disk, `git.dirty == false`, and the tick-exact / capacity overall-pass flags must both be `true`. The JForex adapter's `runId` attaches to a session that is, by construction, running against a validated lock.
- **observed_state:** Code: `validate_oco_live_governance.run` recomputes SHA-256 for every artifact path declared in the lock and compares against the recorded digest; any mismatch fails the gate with `SystemExit(2)`. The `capacity_overall_pass` + `tick_exact_overall_pass` booleans and `live_deployable_consistent` are separately asserted. The runtime check is single-sided on the Python side (JForex has no hash awareness); this surface records that an unverified lock → live-run chain is possible if `make`/`CI` fails to call the validator before starting the session. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** high
- **evidence:** scripts/validate_oco_live_governance.py:110-216; configs/research/governance/oco/audusd_oco_live_lock.json:1-50 (representative lock shape); _replay evidence pending Task 10._
- **harness_check:** no — artifact-hash integrity is verified by a one-shot Python script at deploy/retrain time and is not part of the in-session seed-check loop.
- **fix_owner:** future

### risk_gov.run_id_plumbing

- **layer:** risk_gov
- **python_locus:** src/behemoth/api/server.py:384,1396-1484 (`debug_run_id` override + `_effective_run_id` resolver threaded into every request handler); src/behemoth/api/server.py:2206-2251 (`PredictRequest.run_id` / `runId`); src/behemoth/api/server.py:2442-2476 (`/risk/account/snapshot` consumes `req.run_id` via `_effective_run_id`); src/behemoth/api/server.py:3358-3415 (`/trades/open` + `/trades/active` keyed by run_id for reconciliation); src/behemoth/api/server.py:1053-1054,1680,1873 (audit_logs rows persist `model_month` + `run_id` together)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java:13-39,173 (`runId` field, env-seeded from `BEHEMOTH_JFOREX_RUN_ID`); src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:199-217 (`onAccountSnapshot` sends `sessionConfig.runId()`); BehemothStrategyCore.java:231-244 (predict payload carries `runId`); BehemothStrategyCore.java:335-385 (`handleFill` / `handleClose` send `runId` on `/trades/open` and `/trades/update`); and the batch-ticks path in the same file (`TickBatchRequestPayload` carries `runId`)
- **contract:** Every JForex → Python request for the lifetime of a session will carry the same non-empty `run_id`, set once from `BEHEMOTH_JFOREX_RUN_ID` via `JForexSessionConfig.runId()`. Python joins ticks ↔ predictions ↔ account snapshots ↔ trade opens/updates by `run_id`; a missing, empty, or drifted `run_id` silently splits the session into two logical runs and breaks `/trades/active` reconciliation.
- **observed_state:** Code: Java has a single `runId` resolved at config construction and reuses it on every outbound payload (`TickBatchRequestPayload`, `PredictRequestPayload`, `AccountSnapshotRequestPayload`, `TradeOpenRequestPayload`, `TradeUpdateRequestPayload`). Python's `_effective_run_id` accepts either the request's `run_id` or a `BEHEMOTH_DEBUG_RUN_ID` override; no endpoint rejects an empty/missing `run_id` outright — empty ids coerce to `None` and audit rows store `NULL`, so any drift is only observable via later reconciliation counts. No cross-request invariant asserts "all requests in the current session share the same run_id." Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** high
- **evidence:** _pending Task 10._
- **harness_check:** no — run_id consistency is a per-session invariant observable only via audit_logs/row-join cardinality; no seed check targets it. Partially covered by `lifecycle.active_oco_reconciled` which joins on run_id.
- **fix_owner:** future

### risk_gov.account_snapshot_cadence

- **layer:** risk_gov
- **python_locus:** src/behemoth/api/server.py:2442-2476 (`/risk/account/snapshot` handler → `_state.record_account_snapshot`); src/behemoth/api/server.py:2187 (cost gate's `require_account_snapshot` flag); src/behemoth/risk/account.py:159-224 (`evaluate_account_risk_limits` — returns `snapshot_available=False` → `ACCOUNT_RISK_SNAPSHOT_MISSING` block when no snapshot has been recorded and the profile requires one); src/behemoth/risk/account.py:227-300 (`evaluate_trade_guard` consumes the latest account evaluation)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:199-217 (`onAccountSnapshot(balance, equity, snapshotTs)` fans out `AccountSnapshotRequestPayload` to Python for every currently-subscribed symbol on each broker account event); src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java (`onAccount(IAccount)` → `onAccountSnapshot`; broker-driven cadence)
- **contract:** While a session is running with `require_account_snapshot=true`, each `/predict` call's account-risk evaluation will use a `snapshotTs` within the freshness window implied by the risk profile. The broker-driven `onAccount` cadence must be fast enough that a fresh snapshot arrives between any two consecutive `/predict` calls; stale snapshots must either block trades (`ACCOUNT_RISK_SNAPSHOT_MISSING` / headroom breach) or be tagged `snapshot_available=False`.
- **observed_state:** Code: JForex only pushes a snapshot when the broker fires `onAccount(IAccount)` — frequency depends entirely on Dukascopy's cadence and is not surfaced in configuration. Python's `evaluate_account_risk_limits` uses "latest recorded balance/equity/day_start_balance" with no TTL check; a stale snapshot produces a stale `daily_loss_used` / `max_loss_used` that can cause under-sizing (recent loss not yet reflected → headroom overstated) or over-blocking (recent recovery not yet reflected → headroom understated). There is no freshness assertion in `evaluate_account_risk_limits` beyond `snapshot_available`. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** high
- **evidence:** _pending Task 10._
- **harness_check:** no — snapshot-freshness is a wall-clock invariant that depends on broker cadence; the 8 seed checks do not cover it. Observable via `audit_logs` row pairs (snapshot_ts, predict_ts) at reconciliation time.
- **fix_owner:** future

### risk_gov.entries_allowed_gate

- **layer:** risk_gov
- **python_locus:** _no Python counterpart — the backtest pipeline (`scripts/verify_oco_tick_exact_shortlist.py`) has no readiness-blocked-entries concept; every OPEN_MARKET action is assumed to execute._ src/behemoth/runtime/barrier_manager.py:238-269 (OPEN_MARKET emit path is unconditional relative to live readiness)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:450 (`SymbolRuntimeState.entriesAllowed = true` default); BehemothStrategyCore.java:167-173 (`setEntriesAllowed(symbol, allowed)`); BehemothStrategyCore.java:280-294 (`executeActions` OPEN_MARKET branch: on `entriesAllowed=false` records `entry_blocked_not_ready` via `recordEntryBlocked` and skips the submit); src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessCoordinator.java:285-311 (`syncMetricsAndCore` pushes `symbol.entriesAllowed()` from the readiness FSM into `core.setEntriesAllowed`)
- **contract:** `state.entriesAllowed` is the single client-side gate that can drop a Python-emitted OPEN_MARKET action on the JForex side. Because the backtest pipeline has no equivalent gate, any bar on which live readiness drops (`entriesAllowed=false`) will diverge: live reports `entry_blocked_not_ready`, backtest executes the open. This surface records the known asymmetry and scopes the admissible evidence (blocked entries are not replay-comparable).
- **observed_state:** Code: `LiveReadinessCoordinator` transitions per-symbol state and calls `core.setEntriesAllowed(symbol, symbol.entriesAllowed())` on every readiness publish; default at process start is `true`, flipped to `false` when readiness drops (stale ticks, startup warmup not reached, bridge incomplete). Python has no mirror of this flag — `/predict` does not know which symbols are currently gated on the JForex side, and the offline backtest ingests the parquet end-to-end without any readiness simulation. Consequence: the parity harness must exclude bars where `entries_allowed=false` from the OPEN_MARKET execution-diff checks. Replay evidence: _pending Task 10._
- **divergence:** observed
- **severity:** high
- **evidence:** src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:167-173,280-294,450 (gate code); src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessCoordinator.java:285-311 (FSM → gate plumbing); _replay evidence pending Task 10._
- **harness_check:** yes — core.entries_allowed_vs_readiness
- **fix_owner:** future

## Surfaces — Time & data

_Pending. Populated in Task 5._

## Surfaces — Failure paths

_Pending. Populated in Task 6._

## Replay diff findings

_Pending. Populated in Task 10._

## Harness coverage matrix

_Pending. Populated in Task 25._

## Appendix — Replay diff artifact index

_Pending. Populated in Task 25._

# Bar-Level Barrier Manager Design

## Problem

The live JForex system uses stop-limit order pairs (OCO) to determine trade direction, while the backtest uses bar OHLC to detect barrier touches. This causes three sources of divergence:

1. **Side determination:** The backtest scans bar high/low for barrier breach and uses `hl_first` to break ties. The live system uses whichever stop-limit order fills first at the tick level. These can disagree — on April 1 GBPUSD, one overlapping signal produced BUY +7.6p in backtest vs SELL -7.8p live.
2. **Lifecycle blocking cascade:** Different fill timing shifts which signals get "first pick," causing only 5 of 13 (backtest) / 11 (live) signals to overlap on identical data with identical predictions.
3. **Entry price basis:** The backtest uses bar `close` as reference price; live uses `bid`/`ask` (includes spread). Barrier levels are computed from different starting points.

The backtest's bar-level approach is the proven system — staging analysis models market order risk against it. The live system should match.

## Goal

Replace the stop-limit OCO pair mechanism with a software barrier manager that uses completed bar OHLC to detect barrier touches, producing identical signal selection, side determination, and lifecycle blocking as `_oco_precompute` in the backtest.

## Architecture

The barrier manager lives in the Python API. The Java adapter becomes a thin broker bridge that executes market orders on instruction from the API. All OCO lifecycle logic moves from Java to Python.

### Current Flow

```
Bar completes → Java calls POST /predict → Python returns selected_exec=1
→ Java places two stop-limit entries (BUY above, SELL below)
→ One fills → Java cancels sibling → Java tracks horizon → Java closes at horizon
```

### New Flow

```
Bar completes → Java calls POST /predict → Python checks barrier scans
→ If signal fires: Python registers PendingBarrierScan, returns pending_scan=true
→ On subsequent bar completions: Python checks bar OHLC against barriers
→ If touch confirmed: Python returns action OPEN_MARKET (single side)
→ Java submits single market order
→ After horizon bars: Python returns action CLOSE_MARKET
→ Java closes position at market
```

## Component: BarrierManager

A new component in the Python API that manages pending barrier scans and active positions.

### State (DuckDB table: `barrier_scans`)

| Column | Type | Description |
|--------|------|-------------|
| `scan_id` | VARCHAR PK | Unique scan identifier |
| `symbol` | VARCHAR | |
| `candidate_uid` | VARCHAR | Canonical candidate UID |
| `signal_bar_idx` | INTEGER | Bar ordinal at signal time |
| `ref_price` | DOUBLE | `close` of the signal bar |
| `upper_barrier` | DOUBLE | `ref_price + barrier_pips * pip_size` |
| `lower_barrier` | DOUBLE | `ref_price - barrier_pips * pip_size` |
| `barrier_pips` | DOUBLE | From candidate config |
| `horizon` | INTEGER | From candidate config |
| `scan_bars_remaining` | INTEGER | Counts down from horizon during scan phase |
| `touch_step` | INTEGER | NULL until touched, then the bar offset |
| `touch_side` | VARCHAR | NULL until decided: `BUY` or `SELL` |
| `hold_bars_remaining` | INTEGER | NULL until touched, then counts down from horizon |
| `status` | VARCHAR | `SCANNING` → `HOLDING` → `COMPLETED` or `EXPIRED` |
| `broker_pos_id` | VARCHAR | NULL until trade opened, set on fill confirmation |
| `pred_prob` | DOUBLE | Signal's prediction probability |
| `threshold` | DOUBLE | Threshold at signal time |
| `model_month` | VARCHAR | Model month at signal time |
| `reservation_id` | VARCHAR | Risk reservation ID |
| `run_id` | VARCHAR | |
| `created_ts` | TIMESTAMPTZ | |

### Operations

**`register_scan(symbol, candidate_uid, signal_bar_idx, ref_price, barrier_pips, horizon, pip_size, ...)`**

Creates a new scan with `status=SCANNING`, `scan_bars_remaining=horizon`. Called when `selected_exec=1` passes all gates.

**`evaluate_bar(symbol, bar_ticks, bar_high, bar_low, bar_hl_first, current_bar_idx)`**

Called on every bar completion for the given symbol/bar_ticks. For each `SCANNING` scan:

1. Decrement `scan_bars_remaining`.
2. Check `bar_high >= upper_barrier` (up touch) and `bar_low <= lower_barrier` (down touch).
3. If one side touched: set `touch_side`, `touch_step`, transition to `HOLDING`, set `hold_bars_remaining = horizon`.
4. If both touched in same bar: use `bar_hl_first` to break tie (positive = high first = BUY, negative = low first = SELL). Identical to `_oco_precompute` tie-breaking.
5. If `scan_bars_remaining == 0` with no touch: transition to `EXPIRED`.

For each `HOLDING` scan:

1. Decrement `hold_bars_remaining`.
2. If `hold_bars_remaining == 0`: transition to `COMPLETED`.

Returns a list of actions: `OPEN_MARKET` for new touches, `CLOSE_MARKET` for completed holds.

**`has_active_scan(symbol, candidate_uid) -> bool`**

Returns true if any scan exists with `status IN ('SCANNING', 'HOLDING')`. Used for lifecycle blocking in the prediction path.

### Lifecycle Blocking

The candidate is blocked from the moment a scan is registered until it reaches `COMPLETED` or `EXPIRED`. This matches the backtest's behavior where a signal at bar `i0` blocks the candidate until `i0 + touch_step + horizon` (if touched) or `i0 + horizon` (if no touch).

## API Contract Changes

### `POST /predict` Response

Current response returns a list of prediction items. New response adds an `actions` field:

```json
{
  "predictions": [
    {
      "candidate_uid": "oco|GBPUSD|100|h6|...",
      "pred_prob": 0.625,
      "threshold": 0.599,
      "selected_exec": 1,
      "pending_scan": true,
      "..."
    }
  ],
  "actions": [
    {
      "type": "OPEN_MARKET",
      "symbol": "GBPUSD",
      "side": "SELL",
      "candidate_uid": "oco|GBPUSD|100|h6|...",
      "reservation_id": "abc-123",
      "scan_id": "scan_001"
    },
    {
      "type": "CLOSE_MARKET",
      "symbol": "GBPUSD",
      "broker_pos_id": "272708355",
      "candidate_uid": "oco|GBPUSD|100|h6|...",
      "scan_id": "scan_002"
    }
  ]
}
```

The `actions` list is the sole instruction channel for Java. `selected_exec` remains for audit logging but Java does not act on it directly.

The barrier manager's `evaluate_bar` is called inside the `/predict` handler after feature computation, using the just-completed bar's OHLC from the tick bar buffer. This means barrier evaluation and new signal evaluation happen in the same request cycle, on every bar completion.

### `POST /trades/open` and `POST /trades/update`

Unchanged. Java still reports fills and closes back to the Python API. The barrier manager updates `broker_pos_id` on the scan record when a fill is confirmed.

## Java Adapter Changes

### Removed

- `OcoOrderPlanner` — no paired stop-limit entries
- `OcoOrderPlan` — no paired order plan
- `OcoGroupState` / `OcoLegState` — replaced by Python barrier scan state
- `hasActiveCandidateLifecycle` in `ExecutionStateStore` — lifecycle check moves to Python
- `PendingExit` tracking in `BehemothStrategyCore` — horizon management moves to Python
- Horizon close initiation in `triggerPrediction` — Python issues `CLOSE_MARKET` actions
- `submitOcoPlan` in `BehemothStrategyCore` — replaced by action executor
- `enableNativeOco` — not applicable

### Added/Modified

- `BehemothStrategyCore.triggerPrediction`: after receiving predict response, iterate `actions` list and execute each:
  - `OPEN_MARKET`: call `executionPort.submitMarketOrder(symbol, side, amount)` (new method on `ExecutionPort`)
  - `CLOSE_MARKET`: call `executionPort.closePosition(symbol, label)`
- `ExecutionPort.submitMarketOrder`: new method for single market orders (simpler than `submitStopOrder`)
- `PredictionResponseItem`: add `actions` parsing from JSON response
- `JForexExecutionPort.submitMarketOrder`: JForex IEngine market order submission

### Simplified

- `handleFill`: no sibling cancellation logic needed. Just report fill to Python.
- `handleClose`: no `horizonInitiatedLabels` tracking. Just report close to Python.
- `onOrderEvent`: simpler state machine — `PLANNED → FILLED → CLOSED`.

## Testing

### Parity Test: barrier detection matches `_oco_precompute`

Extract `BarrierManager.evaluate_bar` logic into a testable function. Feed the same bar sequence to both it and `_oco_precompute`. Assert identical `touch_step`, `side`, and `gross_pips` for every signal across a full month of GBPUSD data.

### Parity Test: lifecycle blocking matches backtest

Simulate a sequence of signals through the barrier manager. Use the April 1 GBPUSD data: verify the manager selects the same 13 signals as the backtest and blocks the same bars.

### Integration Test: full e2e replay

Extend `simulate_api_e2e_replay.py` to work with the new `actions`-based flow. Stream a month of ticks, verify that every `OPEN_MARKET` and `CLOSE_MARKET` action matches what `_oco_precompute` would produce.

### Java Tests

- `BehemothStrategyCoreTest`: verify action executor dispatches market orders and closes correctly from mock predict responses containing `actions`.
- `ExecutionPort` tests: verify `submitMarketOrder` sends correct JForex API calls.
- Remove `OcoOrderPlannerTest` and OCO-specific tests.

## Migration

### Governance Config

`oco_hold_mode: from_touch` and `oco_include_no_touch: true` remain unchanged. The barrier manager respects these settings identically to `_oco_precompute`.

### Rollback

Revert to the current branch. The stop-limit OCO approach still works, with the documented parity gap.

### Verification Gate

Before deploying to live: run the e2e replay test on at least one full month of GBPUSD tick data, confirming zero divergence between the barrier manager's actions and `_oco_precompute`'s outputs.

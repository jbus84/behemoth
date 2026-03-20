# JForex Horizon-Based Position Exit Design

## Problem

The real Dukascopy JForex tester (`BehemothJForexStrategy`) never closes filled positions. When the OCO entry stop order fills, the resulting open position stays in `FILLED` status for the entire run because no `CLOSE_OK` event ever arrives. `OcoLegState.isActive()` returns `true` for `FILLED`, so `hasActiveCandidateLifecycle()` blocks all subsequent order submissions for matching `candidateUid` values.

Since each symbol has only 1–2 distinct `candidateUid` values and the warmup fills one position per `candidateUid`, **all eval-window orders are blocked** for all 6 symbols. The Python API correctly returns `selected_exec=1` for these predictions (visible in `audit_logs`), but the Java-side lifecycle gate prevents any order from being submitted.

The local surrogate (`LocalJForexTesterRunner`) avoids this by calling `executionPort.closeOpenOrdersAtEnd()` at run end — a blunt close-all hack. This does not simulate the correct exit timing and does not affect the real Dukascopy tester.

## Requirements

1. After an OCO entry leg fills, the strategy closes the resulting position exactly `horizon` completed bars later (where `horizon` comes from `OcoGroupState.horizon`, typically 5 or 6 for h5/h6 models, and `barTicks` is 100).
2. The close request is issued by the strategy (not the broker): once `horizon` bars have elapsed since fill, the strategy calls `executionPort.closePosition(symbol, label)`.
3. The broker responds with `ORDER_CLOSE_OK`, which routes to `handleClose()` as normal. No other code path changes.
4. `LocalExecutionPort` implements `closePosition` correctly so local-surrogate runs also honour the exit timing.
5. Positions filled during warmup that would exit before `eval_start` clear their lifecycle before any eval-window prediction arrives, allowing normal eval-window order submission.
6. No changes to the Python API, the state schema, or the reconciliation pipeline.

## Architecture

### Bar-ordinal tracking

`BehemothStrategyCore` already maintains `SymbolRuntimeState.barOrdinalsByBarTicks: Map<Integer, Long>`, incremented on every `triggerPrediction` call. This gives a monotonically increasing bar count per `barTicks` granularity since session start.

When a fill arrives (`handleFill`), the strategy records the **fill bar ordinal** for the filled leg: the current value of `barOrdinalsByBarTicks.get(group.barTicks)` at the moment `handleFill` runs.

On every subsequent `triggerPrediction` for the same symbol and `barTicks`, if `currentOrdinal - fillOrdinal >= horizon`, the strategy calls `executionPort.closePosition(symbol, label)`.

### New `ExecutionPort.closePosition`

```java
void closePosition(String symbol, String label);
```

`JForexExecutionPort`: looks up the order by `label` via `engine.getOrder(label)` and calls `order.close()` — identical to the existing `cancelOrder` implementation. (Dukascopy uses `order.close()` for both pending and filled orders.)

`LocalExecutionPort`: emits `CLOSE_OK` with the current bid/ask price and computed PnL pips — identical to the existing `cancelOrder` logic for filled orders. The `cancelOrder` method already handles the filled case correctly, so `closePosition` can delegate to `cancelOrder`.

### Tracking structure

`SymbolRuntimeState` gains a field:

```java
// label -> (fillBarOrdinal, horizon, barTicks)
Map<String, PendingExit> pendingExits = new LinkedHashMap<>();
```

`handleFill` adds an entry. `handleClose` removes it (so a broker-initiated close also removes the pending exit). `triggerPrediction` scans `pendingExits` for the current symbol and calls `closePosition` for any entry where `currentOrdinal - fillBarOrdinal >= horizon`.

### Interaction with existing lifecycle check

Closing a position triggers `handleClose` → `stateStore.markClosed` → leg status transitions from `FILLED` to `CLOSED` → `OcoLegState.isActive()` returns `false` → `hasActiveCandidateLifecycle()` returns `false` for that group → next prediction with the same `candidateUid` can submit a new order. No other code changes.

## Data Flow

```
fill event arrives
  → handleFill records fillBarOrdinal in pendingExits
  → (candidateUid remains active)

bar N completes (triggerPrediction)
  → barOrdinals incremented
  → scan pendingExits: currentOrdinal - fillOrdinal >= horizon?
      yes → executionPort.closePosition(symbol, label)
              → ORDER_CLOSE_OK → handleClose
              → stateStore.markClosed (FILLED → CLOSED)
              → pendingExits entry removed
              → candidateUid lifecycle cleared
      no  → skip
  → Python API called → predictions evaluated
  → lifecycle check passes for cleared candidateUids → orders submitted
```

## Edge Cases

- **Broker closes position before horizon** (e.g. stop-loss hit): `handleClose` removes the `pendingExits` entry; `triggerPrediction` no longer attempts a redundant close.
- **Multiple fills for same barTicks** (two groups fill at the same bar): each tracked independently by label.
- **Fill arrives mid-bar** (between `triggerPrediction` calls): `fillBarOrdinal` is the last completed bar count — the exit fires `horizon` completed bars after the bar in progress at fill time. This is a one-bar imprecision that is acceptable and matches the "h5/h6 bars after entry bar" semantics.
- **Position fills on the last bar of the run**: `closeOpenOrdersAtEnd()` in `LocalExecutionPort` already handles this for the surrogate; for the real tester the position closes at session end via `onStop`.

## Testing

Unit tests in `BehemothStrategyCoreTest` (existing test class or new):

1. Fill at bar 0, horizon=5 → `closePosition` called at bar 5, not before.
2. Fill at bar 0, horizon=6 → `closePosition` called at bar 6.
3. Broker closes position at bar 3 (before horizon=5) → `closePosition` NOT called at bar 5.
4. Two fills in same bar, same symbol → both exits tracked independently.
5. Fill during warmup, horizon elapsed before `eval_start` → lifecycle clears before eval predictions arrive.

Integration: re-run `make jforex-dukascopy-matrix` (or the test harness equivalent); verify `active_oco_state.json` shows no `FILLED` positions at run end, and eval-window order counts > 0 for all symbols.

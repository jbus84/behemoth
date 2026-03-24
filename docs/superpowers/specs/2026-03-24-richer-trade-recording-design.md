# Richer Trade Recording — Design Spec

**Date:** 2026-03-24
**Status:** Approved

---

## Problem

The `trades` table captures the bare minimum: entry/exit price, pnl_pips, status. Several operationally useful fields are either silently dropped or never collected:

- `reservation_id` — sent by JForex in `TradeOpenRequestPayload` and used for risk reservation lifecycle, but never written to the `trades` table itself
- Model context (`pred_prob`, `threshold`, `model_month`) — the prediction that caused the trade is in `audit_logs` but not denormalised into `trades`, making per-trade analytics require a brittle join
- `exit_bar_id` — not stored, so "bars held" (`exit_bar_id - entry_bar_id`) cannot be queried
- `close_reason` — no record of why a trade closed (`HORIZON_COMPLETED` vs `UNEXPECTED`)
- `commission_ccy` — JForex logs show e.g. `commission: -0.46` but this is never sent to Python

---

## Goal

Add 7 new columns to the `trades` table and wire up the collection path end-to-end (JForex → Python API → state.py). No changes to trading logic or risk controls.

---

## New Columns

| Column | Type | Nullable | Source |
|--------|------|----------|--------|
| `reservation_id` | VARCHAR | yes | `TradeOpenRequestPayload.reservationId` — already sent, not yet stored in `trades` |
| `entry_pred_prob` | DOUBLE | yes | Queried from `audit_logs` at open time |
| `entry_threshold` | DOUBLE | yes | Queried from `audit_logs` at open time |
| `entry_model_month` | VARCHAR | yes | Queried from `audit_logs` at open time |
| `exit_bar_id` | INTEGER | yes | `MAX(tick_bars.row_id WHERE symbol=?)` computed at close notification time (see note below) |
| `close_reason` | VARCHAR | yes | JForex determines and sends: `HORIZON_COMPLETED` or `UNEXPECTED` |
| `commission_ccy` | DOUBLE | yes | `IOrder.getCommission()` — stored as-is; negative value means cost (Dukascopy convention) |

All nullable: existing rows (opened before this change) remain valid with NULLs in these columns.

> **`exit_bar_id` approximation note:** Python computes `MAX(tick_bars.row_id)` when the close notification HTTP request arrives. Due to network latency between the broker event and Python receiving the request, the value may overshoot by 0-1 bars. For the primary use case — "approximately how many bars was this trade held" — this is acceptable. Both `entry_bar_id` and `exit_bar_id` use the same MAX-row-id approach so the approximation is consistent.

---

## Architecture

### `reservation_id`

`TradeOpenRequestPayload.reservationId` already carries the value and `TradeOpenRequest` (Python schema) already has `reservation_id: str | None`. The gap is in `server.py`: the `open_trade()` handler receives `req.reservation_id` but does not forward it to `_state.open_trade()`. Fix: add `reservation_id` parameter to `open_trade()` and include it in the INSERT.

### Model context (`entry_pred_prob`, `entry_threshold`, `entry_model_month`)

When `POST /trades/open` is received, `_state.open_trade()` looks up the most recent `audit_logs` row for the same `candidate_uid` and `symbol`:

```sql
SELECT pred_prob, threshold, model_month
FROM audit_logs
WHERE candidate_uid = ? AND symbol = ?
ORDER BY close_ts DESC
LIMIT 1
```

The `symbol` filter is defensive — `candidate_uid` already encodes the symbol, but this prevents cross-symbol contamination if the same uid were written twice due to a bug.

This row is the prediction that triggered the placement. The lookup is safe: `audit_logs` is written before the OCO order reaches the broker, and fill notifications arrive seconds later. If no row is found, store NULLs and log a warning.

### `exit_bar_id`

Python computes `MAX(tick_bars.row_id WHERE symbol=?)` inside `update_trade()`. The `symbol` must be passed as an additional parameter to `update_trade()` (currently it only takes `broker_pos_id`). The server.py update handler already has `req.symbol` available.

### `close_reason`

**How horizon closes work:** `BehemothStrategyCore.triggerPrediction()` checks `pendingExits` each bar. When `currentOrdinal - fillBarOrdinal >= horizon`, the label enters `labelsToClose` and `executionPort.closePosition()` is called. The `CLOSE_OK` event fires `handleClose()` asynchronously after broker confirmation.

**Determining the reason:** Add a `Set<String> horizonInitiatedLabels` to `SymbolRuntimeState`. Inside the close loop in `triggerPrediction`, add the label to the set **before** calling `closePosition()`. If `closePosition()` throws, remove the label from the set in the catch block (the close was never issued). In `handleClose()`, check if the label is present: yes → `HORIZON_COMPLETED`, remove from set; no → `UNEXPECTED`.

```java
// In triggerPrediction close loop:
for (String label : labelsToClose) {
    state.pendingExits.remove(label);
    state.horizonInitiatedLabels.add(label);  // track before calling
    try {
        executionPort.closePosition(state.instrument.symbol(), label);
    } catch (RuntimeException exc) {
        state.horizonInitiatedLabels.remove(label);  // undo if close not issued
        // existing error handling...
    }
}

// In handleClose():
String closeReason = state.horizonInitiatedLabels.remove(event.orderLabel())
    ? "HORIZON_COMPLETED"
    : "UNEXPECTED";
```

Two values:
- `HORIZON_COMPLETED` — bar counter reached `horizon`; normal case
- `UNEXPECTED` — broker closed without a corresponding strategy-initiated request (margin call, weekend close, etc.)

### `commission_ccy`

JForex `IOrder.getCommission()` returns the commission in account currency; negative means cost paid. Stored as-is — no sign normalization. Currently `OrderEvent` has no commission field. Add `Double commission` to `OrderEvent`; populate it in `BehemothJForexStrategy.toOrderEvent()` via `order.getCommission()`. Pass through `TradeUpdateRequestPayload` → `PythonPredictionClient.updateTrade()` → `POST /trades/update` → `update_trade()`.

`LocalExecutionPort` (used in all `BehemothStrategyCoreTest` integration tests) constructs `OrderEvent` directly for simulated events. Since the local harness does not model brokerage costs, pass `null` for `commission` on all `LocalExecutionPort` event constructions — including `SUBMIT_OK`, `FILL_OK`, and `CLOSE_OK`.

---

## Files Changed

### Java

| File | Change |
|------|--------|
| `OrderEvent.java` | Add `Double commission` field |
| `BehemothJForexStrategy.java` | Pass `order.getCommission()` in `toOrderEvent()` constructor call |
| `BehemothStrategyCore.java` | Add `horizonInitiatedLabels` set to `SymbolRuntimeState`; populate in `triggerPrediction()` with exception rollback; determine `closeReason` in `handleClose()`; pass `closeReason` + `commission` to `TradeUpdateRequestPayload` |
| `TradeUpdateRequestPayload.java` | Add `String closeReason`, `Double commissionCcy` |
| `PythonPredictionClient.java` | Pass new fields in `updateTrade()` call |
| `BehemothStrategyCoreTest.java` | Update `new OrderEvent(...)` constructor calls for new `commission` field |
| `LocalExecutionPort.java` | Update all four `new OrderEvent(...)` constructor calls; pass `null` for `commission` |

### Python

| File | Change |
|------|--------|
| `src/behemoth/runtime/state.py` | Add 7 columns to `trades` CREATE TABLE; add `reservation_id` param to `open_trade()` + store it; add `audit_logs` lookup (with `symbol` filter) inside `open_trade()`; add `symbol`, `close_reason`, `commission_ccy` params to `update_trade()` + compute `exit_bar_id` there |
| `src/behemoth/core/schemas.py` | Add `close_reason: str \| None` and `commission_ccy: float \| None` to `TradeUpdateRequest` |
| `src/behemoth/api/server.py` | Pass `reservation_id` to `_state.open_trade()`; pass `req.symbol`, `close_reason`, `commission_ccy` from request to `_state.update_trade()` |

### Tests

| File | Change |
|------|--------|
| `tests/test_duckdb_state.py` | Add tests: `open_trade` stores `reservation_id` + model fields; `update_trade` stores `exit_bar_id`, `close_reason`, `commission_ccy`; `exit_bar_id - entry_bar_id` gives positive bars held |
| `tests/test_api_server.py` | Add tests: `POST /trades/open` passes `reservation_id` through; `POST /trades/update` passes `close_reason` and `commission_ccy` through |

---

## DB Migration

No migration required. All new columns are nullable. Existing rows retain NULLs. New rows written after deployment carry the full set of values. The live database was wiped on 2026-03-24 so there are no legacy rows to preserve.

---

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| `audit_logs` has no matching row at open time | `entry_pred_prob`, `entry_threshold`, `entry_model_month` stored as NULL; warning logged |
| `tick_bars` is empty for symbol at close time | `exit_bar_id` stored as NULL |
| JForex sends `null` for `commissionCcy` | Stored as NULL |
| JForex sends `null` for `closeReason` | Stored as NULL |
| `closePosition()` throws in `triggerPrediction` | Label removed from `horizonInitiatedLabels` in catch block; close reason will be `UNEXPECTED` if broker eventually fires a close event |

---

## Testing

Success criterion: `pytest tests/` and `mvn test` (Java) pass after all changes.

Key assertions by layer:

**Python unit tests (`test_duckdb_state.py`, `test_api_server.py`):**
- `bars_held = exit_bar_id - entry_bar_id` is a positive integer for closed trades
- `close_reason = 'HORIZON_COMPLETED'` round-trips through the API and is stored correctly
- `commission_ccy = -0.46` (synthetic value) round-trips and is stored correctly
- `entry_pred_prob`, `entry_threshold`, `entry_model_month` are populated from `audit_logs` seed row

**Data quality checks (post-run, real trades):**
- `commission_ccy <= 0` for all filled trades (commissions are costs, not income)
- `entry_pred_prob > entry_threshold` for every trade (trading only happens when pred exceeds threshold)

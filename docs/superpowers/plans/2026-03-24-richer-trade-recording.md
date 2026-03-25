# Richer Trade Recording Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 7 new columns to the `trades` table (`reservation_id`, `entry_pred_prob`, `entry_threshold`, `entry_model_month`, `exit_bar_id`, `close_reason`, `commission_ccy`) and wire the full collection path from JForex → Python API → DuckDB state.

**Architecture:** Python changes (Tasks 1–2) are fully independent of Java changes (Tasks 3–4) — both sides use nullable fields so deployment order does not matter. The Java side adds `commission` to `OrderEvent` and a `horizonInitiatedLabels` set to `BehemothStrategyCore` to distinguish `HORIZON_COMPLETED` from `UNEXPECTED` closes.

**Tech Stack:** Python 3.12, FastAPI, DuckDB, Java 21, JForex SDK, pytest, Maven/JUnit 5

---

## File Map

| File | Change |
|------|--------|
| `src/behemoth/runtime/state.py` | Add 7 columns to CREATE TABLE; extend `open_trade()` + `update_trade()` |
| `src/behemoth/core/schemas.py` | Add `close_reason`, `commission_ccy` to `TradeUpdateRequest` |
| `src/behemoth/api/server.py` | Pass new fields through in `/trades/open` and `/trades/update` handlers |
| `tests/test_duckdb_state.py` | New tests for new columns round-trip |
| `tests/test_api_server.py` | New tests for API passthrough |
| `src/jforex/.../core/OrderEvent.java` | Add `Double commission` field |
| `src/jforex/.../BehemothJForexStrategy.java` | Pass `order.getCommission()` in `toOrderEvent()` |
| `src/jforex/.../local/LocalExecutionPort.java` | Add `null` for `commission` in all 4 `new OrderEvent(...)` calls |
| `src/jforex/.../BehemothStrategyCoreTest.java` | Add `null` for `commission` in all `new OrderEvent(...)` calls |
| `src/jforex/.../dto/TradeUpdateRequestPayload.java` | Add `String closeReason`, `Double commissionCcy` |
| `src/jforex/.../core/BehemothStrategyCore.java` | Add `horizonInitiatedLabels`; update `triggerPrediction()` + `handleClose()` |

---

### Task 1: Python — state.py schema and methods

**Files:**
- Modify: `src/behemoth/runtime/state.py`
- Test: `tests/test_duckdb_state.py`

- [ ] **Step 1: Add 7 columns to the `trades` CREATE TABLE**

In `src/behemoth/runtime/state.py`, find the `CREATE TABLE IF NOT EXISTS trades` block (lines 58–74) and replace it:

```python
CREATE TABLE IF NOT EXISTS trades (
    internal_trade_id VARCHAR PRIMARY KEY,
    broker_pos_id VARCHAR,
    symbol VARCHAR,
    candidate_uid VARCHAR,
    side VARCHAR,
    entry_price DOUBLE,
    entry_ts TIMESTAMP WITH TIME ZONE,
    entry_bar_id INTEGER,
    horizon_bars INTEGER,
    touch_bar_id INTEGER,
    exit_price DOUBLE,
    exit_ts TIMESTAMP WITH TIME ZONE,
    pnl_pips DOUBLE,
    status VARCHAR,
    run_id VARCHAR,
    reservation_id VARCHAR,
    entry_pred_prob DOUBLE,
    entry_threshold DOUBLE,
    entry_model_month VARCHAR,
    exit_bar_id INTEGER,
    close_reason VARCHAR,
    commission_ccy DOUBLE
);
```

- [ ] **Step 2: Rewrite `open_trade()` to store `reservation_id` and model context**

Replace the entire `open_trade()` method (lines 386–411):

```python
def open_trade(
    self,
    symbol: str,
    candidate_uid: str,
    broker_pos_id: str,
    side: str,
    entry_price: float,
    entry_ts: datetime,
    horizon: int,
    reservation_id: str | None = None,
    run_id: str | None = None,
) -> str:
    """Record the opening of a position."""
    import uuid
    internal_id = str(uuid.uuid4())

    res = self._con.execute(
        "SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?", [symbol.upper()]
    ).fetchone()
    entry_bar_id = res[0] if res and res[0] is not None else 0

    audit_res = self._con.execute(
        "SELECT pred_prob, threshold, model_month FROM audit_logs "
        "WHERE candidate_uid = ? AND symbol = ? ORDER BY close_ts DESC LIMIT 1",
        [candidate_uid, symbol.upper()],
    ).fetchone()
    if audit_res:
        entry_pred_prob, entry_threshold, entry_model_month = audit_res
    else:
        import logging
        logging.getLogger(__name__).warning(
            "open_trade: no audit_logs row for candidate_uid=%s symbol=%s; model context NULL",
            candidate_uid, symbol,
        )
        entry_pred_prob, entry_threshold, entry_model_month = None, None, None

    self._con.execute(
        """INSERT INTO trades (
            internal_trade_id, broker_pos_id, symbol, candidate_uid, side,
            entry_price, entry_ts, entry_bar_id, horizon_bars, status, run_id,
            reservation_id, entry_pred_prob, entry_threshold, entry_model_month
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?)""",
        [internal_id, broker_pos_id, symbol.upper(), candidate_uid, side,
         float(entry_price), entry_ts, entry_bar_id, horizon, run_id,
         reservation_id, entry_pred_prob, entry_threshold, entry_model_month],
    )
    return internal_id
```

- [ ] **Step 3: Rewrite `update_trade()` to store `exit_bar_id`, `close_reason`, `commission_ccy`**

Replace the entire `update_trade()` method (lines 431–450):

```python
def update_trade(
    self,
    broker_pos_id: str,
    status: str,
    exit_price: float | None = None,
    exit_ts: datetime | None = None,
    pnl_pips: float | None = None,
    run_id: str | None = None,
    symbol: str | None = None,
    close_reason: str | None = None,
    commission_ccy: float | None = None,
) -> None:
    """Update a trade status and exit data (CLOSED/CANCELLED)."""
    exit_bar_id = None
    if symbol:
        res = self._con.execute(
            "SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?", [symbol.upper()]
        ).fetchone()
        exit_bar_id = res[0] if res and res[0] is not None else None

    if run_id:
        self._con.execute(
            "UPDATE trades SET status = ?, exit_price = ?, exit_ts = ?, pnl_pips = ?, "
            "run_id = COALESCE(run_id, ?), exit_bar_id = ?, close_reason = ?, commission_ccy = ? "
            "WHERE broker_pos_id = ?",
            [status, exit_price, exit_ts, pnl_pips, run_id,
             exit_bar_id, close_reason, commission_ccy, broker_pos_id],
        )
        return
    self._con.execute(
        "UPDATE trades SET status = ?, exit_price = ?, exit_ts = ?, pnl_pips = ?, "
        "exit_bar_id = ?, close_reason = ?, commission_ccy = ? "
        "WHERE broker_pos_id = ?",
        [status, exit_price, exit_ts, pnl_pips,
         exit_bar_id, close_reason, commission_ccy, broker_pos_id],
    )
```

- [ ] **Step 4: Write failing tests**

Add a new test class `TestTradeRicherRecording` in `tests/test_duckdb_state.py` after the existing `TestTradeLedger` class:

```python
class TestTradeRicherRecording:
    @pytest.fixture
    def sm(self):
        from src.behemoth.runtime.state import StateManager
        sm = StateManager()
        bars = _make_synthetic_bars(n=3)
        for b in bars:
            sm.append_bar(b)
        yield sm
        sm.close()

    def test_open_trade_stores_reservation_id(self, sm):
        sm.open_trade(
            symbol="EURUSD", candidate_uid="cand_1", broker_pos_id="bp_1",
            side="BUY", entry_price=1.1, entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=6, reservation_id="res-abc-123",
        )
        row = sm._con.execute(
            "SELECT reservation_id FROM trades WHERE broker_pos_id = 'bp_1'"
        ).fetchone()
        assert row[0] == "res-abc-123"

    def test_open_trade_populates_model_context_from_audit_logs(self, sm):
        sm._con.execute(
            "INSERT INTO audit_logs (event_ts, close_ts, symbol, candidate_uid, pred_prob, "
            "threshold, features_json, model_month, run_id) "
            "VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, '{}', ?, ?)",
            [datetime(2025, 1, 1, tzinfo=timezone.utc), "EURUSD", "cand_1", 0.85, 0.72, "2025-01", "r1"],
        )
        sm.open_trade(
            symbol="EURUSD", candidate_uid="cand_1", broker_pos_id="bp_2",
            side="BUY", entry_price=1.1, entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=6,
        )
        row = sm._con.execute(
            "SELECT entry_pred_prob, entry_threshold, entry_model_month FROM trades WHERE broker_pos_id = 'bp_2'"
        ).fetchone()
        assert abs(row[0] - 0.85) < 1e-9
        assert abs(row[1] - 0.72) < 1e-9
        assert row[2] == "2025-01"

    def test_open_trade_nulls_model_context_when_no_audit_row(self, sm):
        sm.open_trade(
            symbol="EURUSD", candidate_uid="no_match", broker_pos_id="bp_3",
            side="BUY", entry_price=1.1, entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=6,
        )
        row = sm._con.execute(
            "SELECT entry_pred_prob, entry_threshold, entry_model_month FROM trades WHERE broker_pos_id = 'bp_3'"
        ).fetchone()
        assert row[0] is None
        assert row[1] is None
        assert row[2] is None

    def test_update_trade_stores_exit_fields(self, sm):
        sm.open_trade(
            symbol="EURUSD", candidate_uid="cand_1", broker_pos_id="bp_4",
            side="BUY", entry_price=1.1, entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=6,
        )
        sm.update_trade(
            broker_pos_id="bp_4",
            status="CLOSED",
            exit_price=1.105,
            exit_ts=datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
            pnl_pips=50.0,
            symbol="EURUSD",
            close_reason="HORIZON_COMPLETED",
            commission_ccy=-0.46,
        )
        row = sm._con.execute(
            "SELECT exit_bar_id, close_reason, commission_ccy FROM trades WHERE broker_pos_id = 'bp_4'"
        ).fetchone()
        assert row[0] is not None  # exit_bar_id computed from tick_bars
        assert row[1] == "HORIZON_COMPLETED"
        assert abs(row[2] - (-0.46)) < 1e-9

    def test_bars_held_is_positive(self, sm):
        sm.open_trade(
            symbol="EURUSD", candidate_uid="cand_1", broker_pos_id="bp_5",
            side="BUY", entry_price=1.1, entry_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            horizon=6,
        )
        # Append more bars so exit_bar_id > entry_bar_id
        for b in _make_synthetic_bars(n=3):
            sm.append_bar(b)
        sm.update_trade(
            broker_pos_id="bp_5",
            status="CLOSED",
            exit_price=1.105,
            exit_ts=datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
            pnl_pips=50.0,
            symbol="EURUSD",
            close_reason="HORIZON_COMPLETED",
        )
        row = sm._con.execute(
            "SELECT entry_bar_id, exit_bar_id FROM trades WHERE broker_pos_id = 'bp_5'"
        ).fetchone()
        assert row[1] > row[0]  # bars_held > 0
```

- [ ] **Step 5: Run tests to verify they fail as expected**

```bash
cd /Users/danielfisher/repositories/behemoth
uv run pytest tests/test_duckdb_state.py::TestTradeRicherRecording -v 2>&1 | tail -20
```

Expected: FAIL — `open_trade()` doesn't accept `reservation_id` yet; `update_trade()` doesn't accept `symbol`.

- [ ] **Step 6: Run tests after implementation to verify they pass**

```bash
uv run pytest tests/test_duckdb_state.py -v 2>&1 | tail -20
```

Expected: all tests pass including `TestTradeRicherRecording`.

- [ ] **Step 7: Commit**

```bash
git add src/behemoth/runtime/state.py tests/test_duckdb_state.py
git commit -m "feat: add 7 new columns to trades table with open/close context"
```

---

### Task 2: Python — schemas.py and server.py passthrough

**Files:**
- Modify: `src/behemoth/core/schemas.py`
- Modify: `src/behemoth/api/server.py`
- Test: `tests/test_api_server.py`

- [ ] **Step 1: Add new fields to `TradeUpdateRequest` in schemas.py**

Find `class TradeUpdateRequest` (around line 292) and add two optional fields:

```python
class TradeUpdateRequest(BaseModel):
    """Sent by the broker adapter when a position is closed or cancelled."""
    symbol: str
    broker_pos_id: str
    status: TradeStatus
    exit_price: float | None = None
    exit_ts: datetime | None = None
    pnl_pips: float | None = None
    run_id: str | None = None
    close_reason: str | None = None
    commission_ccy: float | None = None
```

- [ ] **Step 2: Pass `reservation_id` in the `/trades/open` handler in server.py**

Find the `_state.open_trade(...)` call (around line 2891). Add `reservation_id=req.reservation_id` as a keyword argument:

```python
internal_id = _state.open_trade(
    symbol=req.symbol,
    candidate_uid=req.candidate_uid,
    broker_pos_id=req.broker_pos_id,
    side=req.side,
    entry_price=req.entry_price,
    entry_ts=req.entry_ts,
    horizon=req.horizon,
    reservation_id=req.reservation_id,
    run_id=run_id,
)
```

- [ ] **Step 3: Pass new fields in the `/trades/update` handler in server.py**

Find the `_state.update_trade(...)` call (around line 3197). Add `symbol`, `close_reason`, and `commission_ccy`:

```python
_state.update_trade(
    broker_pos_id=req.broker_pos_id,
    status=req.status.value,
    exit_price=req.exit_price,
    exit_ts=req.exit_ts,
    pnl_pips=req.pnl_pips,
    run_id=run_id,
    symbol=req.symbol,
    close_reason=req.close_reason,
    commission_ccy=req.commission_ccy,
)
```

- [ ] **Step 4: Write failing tests**

Add to the `TestTradeEndpoints` class in `tests/test_api_server.py`:

```python
def test_open_trade_passes_reservation_id(self, client):
    import unittest.mock as mock
    from src.behemoth.api import server

    with mock.patch.object(server._state, 'open_trade', return_value="trade-abc") as mock_open:
        r = client.post("/trades/open", json={
            "symbol": "EURUSD",
            "candidate_uid": "test_cand",
            "broker_pos_id": "456",
            "side": "BUY",
            "entry_price": 1.1000,
            "entry_ts": "2025-01-01T00:00:00Z",
            "horizon": 12,
            "reservation_id": "res-xyz-999",
        })
        assert r.status_code == 200
        call_kwargs = mock_open.call_args.kwargs
        assert call_kwargs["reservation_id"] == "res-xyz-999"

def test_update_trade_passes_close_reason_and_commission(self, client):
    import unittest.mock as mock
    from src.behemoth.api import server

    with mock.patch.object(server._state, 'update_trade') as mock_update:
        r = client.post("/trades/update", json={
            "symbol": "EURUSD",
            "broker_pos_id": "456",
            "status": "CLOSED",
            "exit_price": 1.1050,
            "exit_ts": "2025-01-01T02:00:00Z",
            "pnl_pips": 50.0,
            "close_reason": "HORIZON_COMPLETED",
            "commission_ccy": -0.46,
        })
        assert r.status_code == 200
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["close_reason"] == "HORIZON_COMPLETED"
        assert abs(call_kwargs["commission_ccy"] - (-0.46)) < 1e-9
        assert call_kwargs["symbol"] == "EURUSD"
```

- [ ] **Step 5: Run tests to verify they fail**

```bash
uv run pytest tests/test_api_server.py::TestTradeEndpoints::test_open_trade_passes_reservation_id tests/test_api_server.py::TestTradeEndpoints::test_update_trade_passes_close_reason_and_commission -v 2>&1 | tail -10
```

Expected: FAIL — `open_trade` not yet called with `reservation_id`; `update_trade` not yet called with `close_reason`.

- [ ] **Step 6: Run full Python test suite after implementation**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/behemoth/core/schemas.py src/behemoth/api/server.py tests/test_api_server.py
git commit -m "feat: pass reservation_id, close_reason, commission_ccy through Python API"
```

---

### Task 3: Java — add `commission` to `OrderEvent` and fix all call sites

This task is purely structural — add the new field and update every constructor call. No logic changes.

**Files:**
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/core/OrderEvent.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/local/LocalExecutionPort.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`

- [ ] **Step 1: Add `Double commission` field to `OrderEvent`**

Replace the entire `OrderEvent.java` record:

```java
package com.behemoth.jforex.core;

import java.time.Instant;
import java.util.Objects;

public record OrderEvent(
        OrderEventType type,
        String symbol,
        String orderLabel,
        String brokerOrderId,
        double openPrice,
        Instant fillTimeUtc,
        double closePrice,
        Instant closeTimeUtc,
        Double pnlPips,
        String detail,
        Double commission
) {
    public OrderEvent {
        type = Objects.requireNonNull(type, "type");
        symbol = symbol == null ? "" : symbol.trim().replace("/", "").toUpperCase();
        orderLabel = Objects.requireNonNull(orderLabel, "orderLabel").trim();
        brokerOrderId = Objects.requireNonNullElse(brokerOrderId, "").trim();
        detail = Objects.requireNonNullElse(detail, "");
        if (symbol.isEmpty()) {
            throw new IllegalArgumentException("symbol must not be blank");
        }
        if (orderLabel.isEmpty()) {
            throw new IllegalArgumentException("orderLabel must not be blank");
        }
    }
}
```

- [ ] **Step 2: Update `toOrderEvent()` in `BehemothJForexStrategy.java` to pass `order.getCommission()`**

Find the `return new OrderEvent(...)` call (around line 214). Replace:

```java
return new OrderEvent(
        type,
        normalizeSymbol(order.getInstrument().name()),
        order.getLabel(),
        order.getId(),
        order.getOpenPrice(),
        order.getFillTime() > 0L ? Instant.ofEpochMilli(order.getFillTime()) : null,
        order.getClosePrice(),
        order.getCloseTime() > 0L ? Instant.ofEpochMilli(order.getCloseTime()) : null,
        order.getProfitLossInPips(),
        message.getContent(),
        order.getCommission()
);
```

- [ ] **Step 3: Update `LocalExecutionPort.java` — add `null` for `commission` in all 4 calls**

There are 4 `new OrderEvent(...)` calls: lines 36–47 (SUBMIT_OK), 65–76 (CLOSE_OK / cancel), 101–112 (FILL_OK), 127–138 (CLOSE_OK / end).

Add `null` as the final argument to each. For example line 36–47 becomes:

```java
emit(new OrderEvent(
        OrderEventType.SUBMIT_OK,
        request.symbol(),
        request.label(),
        orderId,
        0.0,
        null,
        0.0,
        null,
        null,
        "local_submit_ok",
        null
));
```

Apply the same pattern (append `null`) to the other three calls at lines 65, 101, 127.

- [ ] **Step 4: Update `BehemothStrategyCoreTest.java` — add `null` for `commission` in all `new OrderEvent(...)` calls**

The test file has 6 `new OrderEvent(...)` calls at lines 490, 571, 583, 665, 670, 747. Each currently ends with a `String detail` argument. Append `, null` to each:

Line 490–494:
```java
core.onOrderEvent(new OrderEvent(
        OrderEventType.FILL_OK, "EURUSD",
        plan.buyLeg().label(), "broker-buy-1",
        1.0857, Instant.parse("2025-07-07T00:00:01Z"),
        0.0, null, null, "fill", null));
```

Apply the same pattern (`"<detail>", null)`) to the remaining 5 calls at lines 571, 583, 665, 670, 747.

- [ ] **Step 5: Run Maven tests to verify all pass**

```bash
cd /Users/danielfisher/repositories/behemoth/src/jforex
mvn test -q 2>&1 | tail -20
```

Expected: `BUILD SUCCESS` — all tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/danielfisher/repositories/behemoth
git add src/jforex/src/main/java/com/behemoth/jforex/core/OrderEvent.java \
        src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java \
        src/jforex/src/main/java/com/behemoth/jforex/local/LocalExecutionPort.java \
        src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java
git commit -m "feat: add commission field to OrderEvent and fix all constructor call sites"
```

---

### Task 4: Java — `TradeUpdateRequestPayload` + `BehemothStrategyCore` close reason wiring

**Files:**
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/runtime/dto/TradeUpdateRequestPayload.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`

- [ ] **Step 1: Add `closeReason` and `commissionCcy` to `TradeUpdateRequestPayload`**

Replace the entire file:

```java
package com.behemoth.jforex.runtime.dto;

import java.time.Instant;

public record TradeUpdateRequestPayload(
        String symbol,
        String brokerPosId,
        String status,
        Double exitPrice,
        Instant exitTs,
        Double pnlPips,
        String runId,
        String closeReason,
        Double commissionCcy
) {
}
```

- [ ] **Step 2: Add `horizonInitiatedLabels` to `SymbolRuntimeState` in `BehemothStrategyCore.java`**

Find the `SymbolRuntimeState` inner class (lines 568–583). Add the new set after `pendingExits`:

```java
private static final class SymbolRuntimeState {
    private final RuntimeInstrument instrument;
    private final List<IncomingTickPayload> pendingTicks = new ArrayList<>();
    private long nextClientTickSeq = 1L;
    private boolean entriesAllowed = true;
    private RuntimeTick lastTick;
    private final Map<Integer, Long> barOrdinalsByBarTicks = new LinkedHashMap<>();
    private final Map<String, PendingExit> pendingExits = new LinkedHashMap<>();
    // Labels for which the strategy has initiated a horizon close. Checked in handleClose()
    // to distinguish HORIZON_COMPLETED (strategy-initiated) from UNEXPECTED (broker-initiated).
    private final Set<String> horizonInitiatedLabels = new LinkedHashSet<>();

    private SymbolRuntimeState(RuntimeInstrument instrument) {
        this.instrument = instrument;
    }
}
```

Also add the required import at the top of the file if not already present:
```java
import java.util.LinkedHashSet;
import java.util.Set;
```

- [ ] **Step 3: Update `triggerPrediction()` close loop to track horizon-initiated closes**

Find the close loop (lines 234–242). Replace it:

```java
for (String label : labelsToClose) {
    state.pendingExits.remove(label);
    state.horizonInitiatedLabels.add(label);
    try {
        executionPort.closePosition(state.instrument.symbol(), label);
    } catch (RuntimeException exc) {
        state.horizonInitiatedLabels.remove(label);
        artifactWriter.markOperationalStep(
                state.instrument.symbol(), "horizon_close_failure", false, exc.getMessage());
    }
}
```

- [ ] **Step 4: Update `handleClose()` to determine `closeReason` and pass commission**

Find `handleClose()` (lines 448–506). The method currently looks up `closeState` near the bottom (line 502). Move that lookup to the top and use it to determine `closeReason`. Replace the full method:

```java
private void handleClose(OrderEvent event) {
    Instant closeTs = Objects.requireNonNullElse(event.closeTimeUtc(), Instant.now());
    SymbolRuntimeState closeState = symbolStates.get(normalizeSymbol(event.symbol()));
    String closeReason = (closeState != null && closeState.horizonInitiatedLabels.remove(event.orderLabel()))
            ? "HORIZON_COMPLETED"
            : "UNEXPECTED";
    ExecutionStateStore.CloseAction action = stateStore.markClosed(
            event.orderLabel(),
            event.closePrice(),
            closeTs,
            event.pnlPips()
    );
    metrics.recordOrderClose(event.symbol(), action.tradeStatus());
    if (action.shouldNotifyTouch()) {
        try {
            predictionClient.touchTrade(new TradeTouchRequestPayload(event.symbol(), event.brokerOrderId(), sessionConfig.runId()));
            if (stateStore.markTradeTouchSynced(event.orderLabel())) {
                artifactWriter.recordTradeTouchSync(event.symbol(), event.brokerOrderId());
            }
        } catch (RuntimeException exc) {
            metrics.recordPythonSyncFailure(event.symbol(), "trade_touch");
            artifactWriter.recordTradeSyncFailure(event.symbol(), "trade_touch_sync_failure", exc.getMessage());
        }
    }
    if (action.shouldNotifyTradeUpdate()) {
        try {
            predictionClient.updateTrade(new TradeUpdateRequestPayload(
                    event.symbol(),
                    event.brokerOrderId(),
                    action.tradeStatus(),
                    event.closePrice(),
                    closeTs,
                    event.pnlPips(),
                    sessionConfig.runId(),
                    closeReason,
                    event.commission()
            ));
            if (stateStore.markTradeUpdateSynced(event.orderLabel())) {
                artifactWriter.recordTradeUpdateSync(event.symbol(), event.brokerOrderId(), action.tradeStatus());
            }
        } catch (RuntimeException exc) {
            metrics.recordPythonSyncFailure(event.symbol(), "trade_update");
            artifactWriter.recordTradeSyncFailure(event.symbol(), "trade_update_sync_failure", exc.getMessage());
        }
    }
    if (action != null && action.group() != null && action.leg() != null) {
        double fillPrice = action.leg().fillPrice != null ? action.leg().fillPrice : Double.NaN;
        double pnlValue = event.pnlPips() != null ? event.pnlPips() : Double.NaN;
        artifactWriter.recordTradeOutcome(
                event.symbol(),
                action.group().groupLabel,
                action.group().candidateUid != null ? action.group().candidateUid : "",
                action.leg().label,
                fillPrice,
                event.closePrice(),
                pnlValue
        );
    }
    if (closeState != null) {
        closeState.pendingExits.remove(event.orderLabel());
    }
    refreshActiveOcoGauge(event.symbol());
}
```

- [ ] **Step 5: Run Maven tests**

```bash
cd /Users/danielfisher/repositories/behemoth/src/jforex
mvn test -q 2>&1 | tail -20
```

Expected: `BUILD SUCCESS`.

If the test `brokerCloseBeforeHorizonCancelsPendingHorizonExit` inspects the body of the `updateTrade` HTTP call, it may need the new fields. Check the mock server request bodies in that test — if `TradeUpdateRequestPayload` serializes to JSON with `close_reason` and `commission_ccy`, the mock server response does not care (it's a recording mock, not a validator). The test should pass as-is.

- [ ] **Step 6: Commit**

```bash
cd /Users/danielfisher/repositories/behemoth
git add src/jforex/src/main/java/com/behemoth/jforex/runtime/dto/TradeUpdateRequestPayload.java \
        src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java
git commit -m "feat: wire close_reason and commission_ccy through JForex trade update payload"
```

---

### Task 5: Final verification

- [ ] **Step 1: Run full Python test suite**

```bash
cd /Users/danielfisher/repositories/behemoth
uv run pytest tests/ -q 2>&1 | tail -10
```

Expected: all tests pass, no errors.

- [ ] **Step 2: Run full Java test suite**

```bash
cd /Users/danielfisher/repositories/behemoth/src/jforex
mvn test -q 2>&1 | tail -10
```

Expected: `BUILD SUCCESS`.

- [ ] **Step 3: Verify no stale `update_trade` call sites missing the new signature**

```bash
cd /Users/danielfisher/repositories/behemoth
grep -rn "update_trade(" src/ tests/ --include="*.py" | grep -v "def update_trade"
```

Inspect each call site — all should either use keyword arguments or already pass the correct positional order (existing callers use keyword args, so new optional params are backward compatible).

- [ ] **Step 4: Verify `open_trade` call sites pass `reservation_id` where available**

```bash
grep -rn "open_trade(" src/ tests/ --include="*.py" | grep -v "def open_trade"
```

Expected: only the server.py handler passes `reservation_id`; all other callers use keyword args and omit it (None default is correct).

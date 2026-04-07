# Live Position Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `GET /trades/open-summary` endpoint, a `live_position_summary.json` file writer, three Prometheus gauges, and three Grafana panels to surface open reservation state (including stuck-PENDING detection) without requiring any JForex changes.

**Architecture:** All data comes from the existing DuckDB state: `account_risk_reservations` for status/direction/age, `trades` for entry price (broker-confirmed positions only), and `tick_bars` for last known close price per symbol. A single helper `_build_open_positions_summary()` computes the response, updates gauges, and is called by both the endpoint and a 5-second background writer.

**Tech Stack:** Python, FastAPI, DuckDB (via existing `StateManager`), prometheus-client, asyncio, Grafana JSON provisioning.

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `src/behemoth/runtime/state.py` | Modify | Add `get_last_bar_close_price(symbol, bar_ticks)` method |
| `src/behemoth/api/server.py` | Modify | Three new gauges, `_build_open_positions_summary()`, `GET /trades/open-summary`, `_write_position_summary_loop()`, lifespan wiring |
| `provisioning/dashboards/behemoth_jforex.json` | Modify | Add three new panels (stat, timeseries, table) |
| `tests/test_api_server.py` | Modify | New `TestOpenSummaryEndpoint` class |

---

### Task 1: Add `get_last_bar_close_price` to StateManager

**Files:**
- Modify: `src/behemoth/runtime/state.py` (after `get_active_trades` at line ~574)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_server.py` inside a new `TestOpenSummaryEndpoint` class:

```python
class TestOpenSummaryEndpoint:
    def test_open_summary_empty(self, client):
        """No open reservations → empty positions list."""
        r = client.get("/trades/open-summary")
        assert r.status_code == 200
        body = r.json()
        assert body["total_open"] == 0
        assert body["broker_confirmed"] == 0
        assert body["pending_broker_confirm"] == 0
        assert body["positions"] == []
        assert "as_of_utc" in body

    def test_get_last_bar_close_price_returns_none_when_no_bars(self, client):
        """StateManager returns None when tick_bars has no rows for symbol."""
        from src.behemoth.api import server
        result = server._state.get_last_bar_close_price("EURUSD")
        assert result is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python3 -m pytest tests/test_api_server.py::TestOpenSummaryEndpoint -x -v 2>&1 | tail -20
```

Expected: FAIL — `AttributeError: 'StateManager' object has no attribute 'get_last_bar_close_price'` and `404` on the endpoint.

- [ ] **Step 3: Add `get_last_bar_close_price` to StateManager**

In `src/behemoth/runtime/state.py`, add after the `get_active_trades` method (around line 583):

```python
def get_last_bar_close_price(
    self, symbol: str, bar_ticks: int = 100
) -> tuple[float, datetime] | None:
    """Return (close_price, close_ts) for the most recent bar, or None if no data."""
    res = self._con.execute(
        "SELECT close_price, close_ts FROM tick_bars "
        "WHERE symbol = ? AND bar_ticks = ? ORDER BY row_id DESC LIMIT 1",
        [symbol.upper(), bar_ticks],
    ).fetchone()
    if res is None:
        return None
    close_price, close_ts = res
    if isinstance(close_ts, datetime):
        close_ts = (
            close_ts.replace(tzinfo=timezone.utc)
            if close_ts.tzinfo is None
            else close_ts.astimezone(timezone.utc)
        )
    return float(close_price), close_ts
```

- [ ] **Step 4: Run the second test to confirm it passes (first still fails — endpoint missing)**

```bash
python3 -m pytest tests/test_api_server.py::TestOpenSummaryEndpoint::test_get_last_bar_close_price_returns_none_when_no_bars -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/runtime/state.py tests/test_api_server.py
git commit -m "feat: add get_last_bar_close_price to StateManager"
```

---

### Task 2: Add Prometheus gauges and `_build_open_positions_summary` helper

**Files:**
- Modify: `src/behemoth/api/server.py`

- [ ] **Step 1: Add the three gauges**

In `src/behemoth/api/server.py`, add after `METRIC_ACCOUNT_RISK_ALLOCATOR_ADMITTED_TOTAL` (around line 198):

```python
METRIC_OPEN_POSITIONS_TOTAL = Gauge(
    "behemoth_open_positions_total",
    "Count of non-closed reservations (PENDING + OPEN)",
    ["symbol"],
)

METRIC_OPEN_POSITION_AGE_SECONDS = Gauge(
    "behemoth_open_position_age_seconds",
    "Wall-clock seconds since the oldest open reservation was created",
    ["symbol"],
)

METRIC_ESTIMATED_UNREALIZED_PIPS = Gauge(
    "behemoth_estimated_unrealized_pips",
    "Best-effort unrealized P&L in pips based on last known bar close price",
    ["symbol"],
)
```

- [ ] **Step 2: Add `_build_open_positions_summary` helper**

In `src/behemoth/api/server.py`, add before the `lifespan` function (around line 430):

```python
def _build_open_positions_summary(state: "StateManager", now: datetime) -> dict:
    """Compute cross-symbol open position summary from DB state.

    Side-effect: updates METRIC_OPEN_POSITIONS_TOTAL, METRIC_OPEN_POSITION_AGE_SECONDS,
    and METRIC_ESTIMATED_UNREALIZED_PIPS for every known symbol.
    """
    reservations = state.list_active_account_risk_reservations()

    # Group by symbol for gauge updates
    by_symbol: dict[str, list[dict]] = {}
    for r in reservations:
        by_symbol.setdefault(r["symbol"], []).append(r)

    positions: list[dict] = []
    for sym, sym_reservations in by_symbol.items():
        price_data = state.get_last_bar_close_price(sym)
        last_tick_price: float | None = price_data[0] if price_data else None
        last_tick_ts: datetime | None = price_data[1] if price_data else None
        last_tick_age_seconds: float | None = (
            round((now - last_tick_ts).total_seconds(), 1) if last_tick_ts else None
        )

        sym_unrealized_total = 0.0
        for r in sym_reservations:
            entry_price: float | None = None
            if r["broker_pos_id"]:
                row = state._con.execute(
                    "SELECT entry_price FROM trades WHERE reservation_id = ? AND status = 'OPEN'",
                    [r["reservation_id"]],
                ).fetchone()
                if row:
                    entry_price = float(row[0])

            estimated_unrealized_pips: float | None = None
            if entry_price is not None and last_tick_price is not None:
                pip_size = _pip_size_for_symbol(sym)
                if r["side"] == "BUY":
                    estimated_unrealized_pips = round(
                        (last_tick_price - entry_price) / pip_size, 1
                    )
                else:
                    estimated_unrealized_pips = round(
                        (entry_price - last_tick_price) / pip_size, 1
                    )
                sym_unrealized_total += estimated_unrealized_pips

            created_ts: datetime | None = r["created_ts"]
            open_minutes: float | None = (
                round((now - created_ts).total_seconds() / 60.0, 1)
                if created_ts
                else None
            )
            positions.append(
                {
                    "symbol": sym,
                    "direction": r["side"],
                    "status": r["status"],
                    "broker_confirmed": r["broker_pos_id"] is not None,
                    "broker_pos_id": r["broker_pos_id"],
                    "open_since_utc": created_ts.isoformat() if created_ts else None,
                    "open_minutes": open_minutes,
                    "entry_price": entry_price,
                    "last_tick_price": last_tick_price,
                    "last_tick_age_seconds": last_tick_age_seconds,
                    "estimated_unrealized_pips": estimated_unrealized_pips,
                }
            )

        METRIC_OPEN_POSITIONS_TOTAL.labels(symbol=sym).set(len(sym_reservations))
        oldest = min(
            (r["created_ts"] for r in sym_reservations if r["created_ts"]),
            default=None,
        )
        METRIC_OPEN_POSITION_AGE_SECONDS.labels(symbol=sym).set(
            (now - oldest).total_seconds() if oldest else 0.0
        )
        METRIC_ESTIMATED_UNREALIZED_PIPS.labels(symbol=sym).set(sym_unrealized_total)

    # Zero out gauges for symbols with no open positions
    for sym in state.get_all_symbols():
        if sym not in by_symbol:
            METRIC_OPEN_POSITIONS_TOTAL.labels(symbol=sym).set(0)
            METRIC_OPEN_POSITION_AGE_SECONDS.labels(symbol=sym).set(0)
            METRIC_ESTIMATED_UNREALIZED_PIPS.labels(symbol=sym).set(0)

    broker_confirmed = sum(1 for p in positions if p["broker_confirmed"])
    return {
        "as_of_utc": now.isoformat(),
        "total_open": len(positions),
        "broker_confirmed": broker_confirmed,
        "pending_broker_confirm": len(positions) - broker_confirmed,
        "positions": positions,
    }
```

Note: `StateManager` is referenced as a string annotation here to avoid a circular import — it is already imported at runtime. If the file uses `TYPE_CHECKING` blocks, add `StateManager` there; otherwise the string annotation is fine.

- [ ] **Step 3: Write a test for the helper with a mock reservation**

Add to `TestOpenSummaryEndpoint` in `tests/test_api_server.py`:

```python
def test_build_summary_with_pending_reservation(self, client):
    """PENDING reservation with no broker_pos_id → entry_price null, unrealized null."""
    import unittest.mock as mock
    from datetime import datetime, timezone, timedelta
    from src.behemoth.api import server

    now = datetime(2026, 4, 7, 14, 15, 0, tzinfo=timezone.utc)
    created = now - timedelta(minutes=12, seconds=30)
    fake_reservation = {
        "reservation_id": "res-001",
        "created_ts": created,
        "updated_ts": created,
        "symbol": "USDCHF",
        "candidate_uid": "cand-001",
        "broker_pos_id": None,
        "status": "PENDING",
        "reserved_loss_ccy": 10.0,
        "barrier_pips": 20.0,
        "cap_pips": 30.0,
        "cost_est_pips": 5.0,
        "volume_units": 1000.0,
        "side": "BUY",
        "source": "algo",
    }
    with (
        mock.patch.object(
            server._state,
            "list_active_account_risk_reservations",
            return_value=[fake_reservation],
        ),
        mock.patch.object(server._state, "get_last_bar_close_price", return_value=None),
        mock.patch.object(server._state, "get_all_symbols", return_value=["USDCHF"]),
    ):
        summary = server._build_open_positions_summary(server._state, now)

    assert summary["total_open"] == 1
    assert summary["broker_confirmed"] == 0
    assert summary["pending_broker_confirm"] == 1
    pos = summary["positions"][0]
    assert pos["symbol"] == "USDCHF"
    assert pos["status"] == "PENDING"
    assert pos["broker_confirmed"] is False
    assert pos["broker_pos_id"] is None
    assert pos["entry_price"] is None
    assert pos["estimated_unrealized_pips"] is None
    assert pos["open_minutes"] == 12.5
```

- [ ] **Step 4: Run the helper test**

```bash
python3 -m pytest tests/test_api_server.py::TestOpenSummaryEndpoint::test_build_summary_with_pending_reservation -v 2>&1 | tail -15
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/api/server.py tests/test_api_server.py
git commit -m "feat: add open positions summary helper and Prometheus gauges"
```

---

### Task 3: Add `GET /trades/open-summary` endpoint

**Files:**
- Modify: `src/behemoth/api/server.py`

- [ ] **Step 1: Add the endpoint**

In `src/behemoth/api/server.py`, add after the `GET /trades/summary` endpoint (around line 3071):

```python
@app.get("/trades/open-summary")
async def get_open_positions_summary():
    """Cross-symbol view of all non-closed reservations with best-effort unrealized P&L."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    now = datetime.now(tz=timezone.utc)
    return _build_open_positions_summary(_state, now)
```

- [ ] **Step 2: Run the empty-summary endpoint test (already written in Task 1)**

```bash
python3 -m pytest tests/test_api_server.py::TestOpenSummaryEndpoint::test_open_summary_empty -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 3: Add an endpoint test with a live PENDING reservation**

Add to `TestOpenSummaryEndpoint` in `tests/test_api_server.py`:

```python
def test_open_summary_with_pending_reservation(self, client):
    """Endpoint returns one PENDING position with correct shape."""
    import unittest.mock as mock
    from datetime import datetime, timezone, timedelta
    from src.behemoth.api import server

    now_fixed = datetime(2026, 4, 7, 14, 15, 0, tzinfo=timezone.utc)
    created = now_fixed - timedelta(minutes=5)
    fake_reservation = {
        "reservation_id": "res-001",
        "created_ts": created,
        "updated_ts": created,
        "symbol": "EURUSD",
        "candidate_uid": "cand-001",
        "broker_pos_id": None,
        "status": "PENDING",
        "reserved_loss_ccy": 10.0,
        "barrier_pips": 20.0,
        "cap_pips": 30.0,
        "cost_est_pips": 5.0,
        "volume_units": 1000.0,
        "side": "BUY",
        "source": "algo",
    }
    with (
        mock.patch.object(
            server._state,
            "list_active_account_risk_reservations",
            return_value=[fake_reservation],
        ),
        mock.patch.object(server._state, "get_last_bar_close_price", return_value=None),
        mock.patch.object(server._state, "get_all_symbols", return_value=["EURUSD"]),
    ):
        r = client.get("/trades/open-summary")

    assert r.status_code == 200
    body = r.json()
    assert body["total_open"] == 1
    assert body["pending_broker_confirm"] == 1
    assert len(body["positions"]) == 1
    pos = body["positions"][0]
    assert pos["symbol"] == "EURUSD"
    assert pos["status"] == "PENDING"
    assert pos["broker_confirmed"] is False
    assert pos["entry_price"] is None
    assert pos["estimated_unrealized_pips"] is None

def test_open_summary_uninitialized_state(self, client):
    """Returns 503 when state manager is not initialized."""
    from src.behemoth.api import server

    original = server._state
    server._state = None
    try:
        r = client.get("/trades/open-summary")
        assert r.status_code == 503
    finally:
        server._state = original
```

- [ ] **Step 4: Run all open-summary endpoint tests**

```bash
python3 -m pytest tests/test_api_server.py::TestOpenSummaryEndpoint -v 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/api/server.py tests/test_api_server.py
git commit -m "feat: add GET /trades/open-summary endpoint"
```

---

### Task 4: Add background file writer and wire into lifespan

**Files:**
- Modify: `src/behemoth/api/server.py`

- [ ] **Step 1: Add `_write_position_summary_loop`**

In `src/behemoth/api/server.py`, add after `_monitor_ledger` (around line 573):

```python
async def _write_position_summary_loop() -> None:
    """Background task: write live_position_summary.json every 5 seconds."""
    while True:
        try:
            if _state and _config.persist_db_path:
                now = datetime.now(tz=timezone.utc)
                summary = _build_open_positions_summary(_state, now)
                summary_path = (
                    Path(_config.persist_db_path).parent / "live_position_summary.json"
                )
                summary_path.write_text(
                    json.dumps(summary, indent=2, default=str), encoding="utf-8"
                )
        except Exception as e:
            logger.error("Position summary writer error: %s", e)
        await asyncio.sleep(5)
```

- [ ] **Step 2: Wire the background task into `lifespan`**

In `src/behemoth/api/server.py`, find the `lifespan` function (around line 441). Add `position_summary_task` alongside `monitor_task`:

```python
    # Start background monitor
    monitor_task = asyncio.create_task(_monitor_ledger())
    position_summary_task = asyncio.create_task(_write_position_summary_loop())
```

And in the cleanup section (around line 536), cancel it:

```python
    _lifespan_ready = False
    monitor_task.cancel()
    position_summary_task.cancel()
    with suppress(asyncio.CancelledError):
        await monitor_task
    with suppress(asyncio.CancelledError):
        await position_summary_task
```

- [ ] **Step 3: Add a test confirming the writer skips writing when persist_db_path is unset**

Add to `TestOpenSummaryEndpoint` in `tests/test_api_server.py`:

```python
def test_position_summary_writer_skips_without_persist_path(self, client):
    """Writer loop does not write when persist_db_path is falsy."""
    import asyncio
    import unittest.mock as mock
    from src.behemoth.api import server

    original_path = server._config.persist_db_path
    server._config.persist_db_path = ""
    try:
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            # Run the loop body once via asyncio
            asyncio.get_event_loop().run_until_complete(
                asyncio.wait_for(server._write_position_summary_loop(), timeout=0.1)
            )
    except (asyncio.TimeoutError, Exception):
        pass
    finally:
        server._config.persist_db_path = original_path
    # If persist_db_path is falsy, open() is never called
    mock_file.assert_not_called()
```

- [ ] **Step 4: Run all open-summary tests**

```bash
python3 -m pytest tests/test_api_server.py::TestOpenSummaryEndpoint -v 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
python3 -m pytest tests/test_api_server.py -x -q --tb=short 2>&1 | tail -15
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/behemoth/api/server.py tests/test_api_server.py
git commit -m "feat: add position summary background file writer"
```

---

### Task 5: Add Grafana panels to `behemoth_jforex.json`

**Files:**
- Modify: `provisioning/dashboards/behemoth_jforex.json`

- [ ] **Step 1: Add the three panels to the panels array**

In `provisioning/dashboards/behemoth_jforex.json`, append the following three objects to the `"panels"` array (before the closing `]`). Current max panel id is 10, max y is 32.

**Panel 11 — Open Positions stat (cross-symbol count):**
```json
{
  "datasource": {
    "type": "prometheus",
    "uid": "behemoth-prometheus"
  },
  "fieldConfig": {
    "defaults": {
      "color": { "mode": "thresholds" },
      "thresholds": {
        "mode": "absolute",
        "steps": [
          { "color": "green", "value": null },
          { "color": "yellow", "value": 1 },
          { "color": "red", "value": 4 }
        ]
      },
      "unit": "short"
    },
    "overrides": []
  },
  "gridPos": { "h": 4, "w": 4, "x": 0, "y": 40 },
  "id": 11,
  "options": {
    "colorMode": "background",
    "graphMode": "none",
    "justifyMode": "auto",
    "orientation": "auto",
    "reduceOptions": {
      "calcs": ["lastNotNull"],
      "fields": "",
      "values": false
    },
    "textMode": "auto"
  },
  "targets": [
    {
      "datasource": { "type": "prometheus", "uid": "behemoth-prometheus" },
      "editorMode": "code",
      "expr": "sum(behemoth_open_positions_total)",
      "legendFormat": "Open Positions",
      "range": false,
      "instant": true,
      "refId": "A"
    }
  ],
  "title": "Open Positions (total)",
  "type": "stat"
}
```

**Panel 12 — Estimated unrealized pips per symbol (time-series):**
```json
{
  "datasource": {
    "type": "prometheus",
    "uid": "behemoth-prometheus"
  },
  "fieldConfig": {
    "defaults": {
      "color": { "mode": "palette-classic" },
      "unit": "short"
    },
    "overrides": []
  },
  "gridPos": { "h": 8, "w": 12, "x": 4, "y": 40 },
  "id": 12,
  "options": {
    "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true },
    "tooltip": { "mode": "single", "sort": "none" }
  },
  "targets": [
    {
      "datasource": { "type": "prometheus", "uid": "behemoth-prometheus" },
      "editorMode": "code",
      "expr": "behemoth_estimated_unrealized_pips",
      "legendFormat": "{{symbol}}",
      "range": true,
      "refId": "A"
    }
  ],
  "title": "Estimated Unrealized Pips by Symbol",
  "type": "timeseries"
}
```

**Panel 13 — Open position age by symbol (table):**
```json
{
  "datasource": {
    "type": "prometheus",
    "uid": "behemoth-prometheus"
  },
  "fieldConfig": {
    "defaults": {
      "color": { "mode": "thresholds" },
      "thresholds": {
        "mode": "absolute",
        "steps": [
          { "color": "green", "value": null },
          { "color": "yellow", "value": 300 },
          { "color": "red", "value": 900 }
        ]
      },
      "unit": "s"
    },
    "overrides": []
  },
  "gridPos": { "h": 8, "w": 8, "x": 16, "y": 40 },
  "id": 13,
  "options": {
    "footer": { "enablePagination": false },
    "showHeader": true
  },
  "targets": [
    {
      "datasource": { "type": "prometheus", "uid": "behemoth-prometheus" },
      "editorMode": "code",
      "expr": "behemoth_open_position_age_seconds > 0",
      "legendFormat": "{{symbol}}",
      "instant": true,
      "range": false,
      "refId": "A"
    }
  ],
  "title": "Open Position Age by Symbol",
  "type": "table"
}
```

- [ ] **Step 2: Validate the JSON is well-formed**

```bash
python3 -c "import json; json.load(open('provisioning/dashboards/behemoth_jforex.json')); print('JSON valid')"
```

Expected: `JSON valid`

- [ ] **Step 3: Commit**

```bash
git add provisioning/dashboards/behemoth_jforex.json
git commit -m "feat: add open position observability panels to JForex Grafana dashboard"
```

---

### Task 6: Final integration verification

- [ ] **Step 1: Run the full test suite**

```bash
python3 -m pytest tests/test_api_server.py -q --tb=short 2>&1 | tail -15
```

Expected: all tests pass, no regressions.

- [ ] **Step 2: Smoke-test the endpoint manually**

Start the API server in a separate terminal:
```bash
make api-start  # or: python3 -m uvicorn src.behemoth.api.server:app --port 8000
```

Then:
```bash
curl -s http://localhost:8000/trades/open-summary | python3 -m json.tool
```

Expected: JSON with `total_open`, `broker_confirmed`, `pending_broker_confirm`, `positions` array, `as_of_utc`.

- [ ] **Step 3: Verify Prometheus metrics appear**

```bash
curl -s http://localhost:8000/metrics | grep behemoth_open
```

Expected: lines for `behemoth_open_positions_total`, `behemoth_open_position_age_seconds`, `behemoth_estimated_unrealized_pips`.

- [ ] **Step 4: Create PR**

```bash
git push origin HEAD
gh pr create \
  --title "feat: live position observability (open-summary endpoint + metrics + Grafana)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `GET /trades/open-summary` endpoint for cross-symbol open reservation view
- Writes `live_position_summary.json` every 5s alongside existing readiness file
- Three new Prometheus gauges: open count, age, estimated unrealized pips per symbol
- Three new Grafana panels in `behemoth_jforex.json`: stat, timeseries, table

## Test plan
- [ ] `python3 -m pytest tests/test_api_server.py::TestOpenSummaryEndpoint -v` — all pass
- [ ] `python3 -m pytest tests/test_api_server.py -q` — no regressions
- [ ] `curl http://localhost:8000/trades/open-summary` returns correct JSON shape
- [ ] `curl http://localhost:8000/metrics | grep behemoth_open` shows 3 new gauges
- [ ] Grafana dashboard loads and new panels render

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

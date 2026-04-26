# StateManager Seam — Design Spec

**Date:** 2026-04-26
**Goal:** Close the 11 raw `_con.execute` leaks in `server.py` by adding the missing methods to `StateManager`, making the Live Runtime's HTTP layer free of direct SQL.

---

## Context

`src/behemoth/api/server.py` bypasses `StateManager`'s interface in 11 places, calling `_state._con.execute(...)` directly. This means:

- SQL logic is scattered across the HTTP layer instead of concentrated in the Repository
- The position summary, warmup, and touch paths are untestable without standing up FastAPI
- Locality is broken — a change to the `tick_bars` schema requires hunting across `state.py` and `server.py`

A twelfth bypass (`BarrierManager(con=_state._con)`) is excluded from this change — `BarrierManager` shares the connection by design and warrants its own treatment.

---

## Approach

Add 8 new methods to `StateManager`. Replace the 11 call sites in `server.py` with those methods. No logic moves — only SQL disappears from the HTTP layer.

This is the first of three sequential branches:
1. **This branch** — StateManager seam
2. Next — PredictionEngine extraction
3. Next — Account-risk orchestration extraction

---

## New StateManager Methods

All methods added to `src/behemoth/runtime/state.py`.

### `get_open_trade_entry_price(reservation_id: str) -> float | None`

```python
def get_open_trade_entry_price(self, reservation_id: str) -> float | None:
```

Replaces line 604. Returns the `entry_price` of the OPEN trade for the given reservation, or `None` if not found.

```sql
SELECT entry_price FROM trades
WHERE reservation_id = ? AND status = 'OPEN'
```

---

### `get_latest_bar_id(symbol: str) -> int`

```python
def get_latest_bar_id(self, symbol: str) -> int:
```

Replaces lines 662 and 3933 (identical query, two call sites). Returns `MAX(row_id)` from `tick_bars` for the symbol, or `0` if no rows exist.

```sql
SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?
```

---

### `get_latest_tick_snapshot(symbol: str) -> tuple[float, datetime] | None`

```python
def get_latest_tick_snapshot(self, symbol: str) -> tuple[float, datetime] | None:
```

Replaces line 1165. Returns `(close_bid, close_ts)` for the most recent bar for the symbol across all `bar_ticks` values, or `None` if no data. Distinct from the existing `get_last_bar_close_price` which filters by `bar_ticks`.

```sql
SELECT close_bid, close_ts FROM tick_bars
WHERE symbol = ?
ORDER BY row_id DESC
LIMIT 1
```

Returns `close_ts` as a UTC-aware `datetime`.

---

### `clear_audit_logs_by_run_id(run_id: str) -> None`

```python
def clear_audit_logs_by_run_id(self, run_id: str) -> None:
```

Replaces line 1117. Deletes all `audit_logs` rows matching the given `run_id`.

```sql
DELETE FROM audit_logs WHERE run_id = ?
```

---

### `export_warmup_bars(symbol: str, bar_ticks: int, path: Path) -> int`

```python
def export_warmup_bars(self, symbol: str, bar_ticks: int, path: Path) -> int:
```

Replaces line 3412. Writes all `tick_bars` rows for the given symbol and bar_ticks to a Parquet file at `path`, ordered by `row_id`. Returns the row count written.

The caller is responsible for creating a temp file and deleting it after use. `StateManager` never touches Polars or pandas — it writes via DuckDB's native `COPY ... TO ... (FORMAT PARQUET)`.

**Caller pattern:**
```python
with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
    tmp_path = Path(f.name)
# delete=False because NamedTemporaryFile with delete=True closes+deletes before the caller can read it
try:
    row_count = _state.export_warmup_bars(sym, bar_ticks, tmp_path)
    bars_df = pl.read_parquet(tmp_path)
finally:
    tmp_path.unlink(missing_ok=True)
```

This is also where `server.py`'s warmup path migrates from pandas to Polars. Only this one path changes format; nothing else in `server.py` changes.

---

### `count_audit_logs(symbol: str, run_id: str) -> int`

```python
def count_audit_logs(self, symbol: str, run_id: str) -> int:
```

Replaces line 3536. Returns the count of `audit_logs` rows for the given symbol and run_id.

```sql
SELECT COUNT(*) FROM audit_logs WHERE symbol = ? AND run_id = ?
```

---

### `atomic_audit_replace(symbol: str, run_id: str, events_batch: list[tuple]) -> int`

```python
def atomic_audit_replace(self, symbol: str, run_id: str, events_batch: list[tuple]) -> int:
```

Replaces lines 3557–3563. Wraps `purge_audit_events` + `log_audit_event_batch` in a single `BEGIN`/`COMMIT` transaction. Returns the number of rows purged. Rolls back and re-raises on any exception.

```python
self._con.execute("BEGIN TRANSACTION")
try:
    purged = self.purge_audit_events(symbol=symbol, run_id=run_id)
    self.log_audit_event_batch(events_batch)
    self._con.execute("COMMIT")
    return purged
except Exception:
    with suppress(Exception):
        self._con.execute("ROLLBACK")
    raise
```

---

### `checkpoint() -> None`

```python
def checkpoint(self) -> None:
```

Replaces line 3664. Forces DuckDB to flush the WAL to the on-disk database file.

```sql
CHECKPOINT
```

---

## Changes to server.py

Each of the 11 call sites is replaced with the corresponding method. No logic moves.

`_latest_tick_price_snapshot` (line 1162) stays in `server.py` as a formatting wrapper — it calls `state.get_latest_tick_snapshot(sym)` and builds the same dict shape the rest of the server expects.

The warmup path (around line 3412) changes from a pandas DataFrame fetch to the Polars pattern shown above under `export_warmup_bars`.

**No other changes to `server.py`.**

---

## Tests

New tests in `tests/test_state_manager.py` (or `tests/test_state_manager_queries.py` if the existing file is large) covering each of the 8 new methods. Tests use an in-memory DuckDB `StateManager` — same pattern as existing `StateManager` tests.

Each test:
- Sets up minimal table state
- Calls the method
- Asserts the return value and/or side effect

The `atomic_audit_replace` test must verify rollback behaviour: if `log_audit_event_batch` raises, no rows are purged.

---

## Out of Scope

- `BarrierManager(con=_state._con)` — excluded, warrants separate treatment
- `_con` visibility (`__con` name mangling) — excluded, too disruptive with `BarrierManager` in play
- PredictionEngine extraction — next branch
- Account-risk extraction — branch after that
- Polars migration beyond the warmup path — out of scope

# StateManager Seam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close 11 raw `_con.execute` leaks in `server.py` by adding 8 missing methods to `StateManager`, so the HTTP layer contains no direct SQL.

**Architecture:** Add methods to `StateManager` (`src/behemoth/runtime/state.py`) and replace each call site in `server.py` (`src/behemoth/api/server.py`). No logic moves — only SQL disappears from the HTTP layer. The warmup path additionally migrates from pandas to Polars as part of replacing its call site. All new methods get unit tests in a new `tests/test_state_manager_queries.py`.

**Tech Stack:** Python, pytest, DuckDB (`StateManager`), Polars (warmup read path only).

**Design spec:** `docs/superpowers/specs/2026-04-26-state-manager-seam-design.md`

---

## File Structure

- Modify: `src/behemoth/runtime/state.py` — add 8 new methods before `close()`
- Modify: `src/behemoth/api/server.py` — replace 11 `_con.execute` call sites
- Create: `tests/test_state_manager_queries.py` — unit tests for the 8 new methods

---

## Task 1: Trade and bar read methods

**Files:**
- Modify: `src/behemoth/runtime/state.py`
- Create: `tests/test_state_manager_queries.py`

These three methods read from `trades` and `tick_bars`. They share test setup (an in-memory `StateManager` with a few rows inserted via existing public methods).

- [ ] **Step 1: Create the test file with a shared fixture**

Create `tests/test_state_manager_queries.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.behemoth.runtime.state import StateManager
from src.behemoth.core.schemas import IncomingTickBar


@pytest.fixture
def sm():
    state = StateManager()
    yield state
    state.close()


def _make_bar(symbol: str, bar_ticks: int, row_num: int, close_bid: float = 1.1000) -> IncomingTickBar:
    """Helper: build a minimal IncomingTickBar for test data insertion."""
    ts = datetime(2026, 1, 1, 0, row_num, tzinfo=timezone.utc)
    return IncomingTickBar(
        symbol=symbol,
        bar_ticks=bar_ticks,
        timestamp=ts,
        close_ts=ts,
        open_bid=close_bid,
        high_bid=close_bid + 0.001,
        low_bid=close_bid - 0.001,
        close_bid=close_bid,
        spread=0.0001,
        tick_volume=100.0,
        high_ask=close_bid + 0.0001,
        close_ask=close_bid + 0.0001,
    )
```

- [ ] **Step 2: Write failing tests for get_open_trade_entry_price**

Append to `tests/test_state_manager_queries.py`:

```python
def test_get_open_trade_entry_price_returns_price(sm):
    sm.open_trade(
        symbol="EURUSD",
        candidate_uid="cand-001",
        broker_pos_id="broker-001",
        side="BUY",
        entry_price=1.2345,
        entry_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        horizon=50,
        reservation_id="res-001",
    )
    result = sm.get_open_trade_entry_price("res-001")
    assert result == pytest.approx(1.2345)


def test_get_open_trade_entry_price_returns_none_when_not_found(sm):
    result = sm.get_open_trade_entry_price("nonexistent-res")
    assert result is None
```

- [ ] **Step 3: Write failing tests for get_latest_bar_id**

Append to `tests/test_state_manager_queries.py`:

```python
def test_get_latest_bar_id_returns_max_row_id(sm):
    sm.append_bar(_make_bar("EURUSD", 100, 1))
    sm.append_bar(_make_bar("EURUSD", 100, 2))
    sm.append_bar(_make_bar("EURUSD", 100, 3))
    result = sm.get_latest_bar_id("EURUSD")
    assert result == 2  # row_id is 0-indexed: rows 0, 1, 2


def test_get_latest_bar_id_returns_zero_when_no_rows(sm):
    result = sm.get_latest_bar_id("NOSYMBOL")
    assert result == 0
```

- [ ] **Step 4: Write failing tests for get_latest_tick_snapshot**

Append to `tests/test_state_manager_queries.py`:

```python
def test_get_latest_tick_snapshot_returns_most_recent_bar(sm):
    sm.append_bar(_make_bar("EURUSD", 100, 1, close_bid=1.1000))
    sm.append_bar(_make_bar("EURUSD", 200, 2, close_bid=1.2000))  # different bar_ticks, later row
    result = sm.get_latest_tick_snapshot("EURUSD")
    assert result is not None
    price, ts = result
    assert price == pytest.approx(1.2000)
    assert ts.tzinfo is not None


def test_get_latest_tick_snapshot_returns_none_when_no_rows(sm):
    result = sm.get_latest_tick_snapshot("NOSYMBOL")
    assert result is None
```

- [ ] **Step 5: Run tests to confirm they all fail**

```bash
cd /path/to/worktree
uv run pytest tests/test_state_manager_queries.py -v 2>&1 | tail -15
```

Expected: 6 failures — `AttributeError: 'StateManager' object has no attribute 'get_open_trade_entry_price'` (and similar for the others).

- [ ] **Step 6: Implement the three methods in state.py**

Add these three methods to `src/behemoth/runtime/state.py` immediately before the `close()` method:

```python
def get_open_trade_entry_price(self, reservation_id: str) -> float | None:
    """Return entry_price of the OPEN trade for the given reservation, or None."""
    row = self._con.execute(
        "SELECT entry_price FROM trades WHERE reservation_id = ? AND status = 'OPEN'",
        [reservation_id],
    ).fetchone()
    return float(row[0]) if row else None

def get_latest_bar_id(self, symbol: str) -> int:
    """Return MAX(row_id) for tick_bars of this symbol, or 0 if no rows exist."""
    row = self._con.execute(
        "SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?",
        [symbol.upper()],
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0

def get_latest_tick_snapshot(self, symbol: str) -> tuple[float, datetime] | None:
    """Return (close_bid, close_ts) for the most recent bar across all bar_ticks, or None."""
    row = self._con.execute(
        "SELECT close_bid, close_ts FROM tick_bars WHERE symbol = ? ORDER BY row_id DESC LIMIT 1",
        [symbol.upper()],
    ).fetchone()
    if not row or row[0] is None:
        return None
    close_ts = row[1]
    if isinstance(close_ts, datetime):
        close_ts = (
            close_ts.replace(tzinfo=timezone.utc)
            if close_ts.tzinfo is None
            else close_ts.astimezone(timezone.utc)
        )
    return float(row[0]), close_ts
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
uv run pytest tests/test_state_manager_queries.py -v 2>&1 | tail -15
```

Expected: 6 tests pass.

- [ ] **Step 8: Commit**

```bash
git add tests/test_state_manager_queries.py src/behemoth/runtime/state.py
git commit -m "feat: add get_open_trade_entry_price, get_latest_bar_id, get_latest_tick_snapshot to StateManager"
```

---

## Task 2: Audit log read and delete methods

**Files:**
- Modify: `src/behemoth/runtime/state.py`
- Modify: `tests/test_state_manager_queries.py`

- [ ] **Step 1: Write failing tests for clear_audit_logs_by_run_id and count_audit_logs**

Append to `tests/test_state_manager_queries.py`:

```python
def _insert_audit_row(sm: StateManager, symbol: str, run_id: str) -> None:
    """Insert a minimal audit_logs row via the public batch API."""
    from datetime import datetime, timezone
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Tuple shape: (close_ts, symbol, candidate_uid, pred_prob, threshold, features_json, model_month, run_id)
    sm.log_audit_event_batch([
        (ts, symbol.upper(), "cand-001", 0.8, 0.5, "{}", "2026-01", run_id)
    ])


def test_count_audit_logs_returns_correct_count(sm):
    _insert_audit_row(sm, "EURUSD", "run-a")
    _insert_audit_row(sm, "EURUSD", "run-a")
    _insert_audit_row(sm, "EURUSD", "run-b")
    assert sm.count_audit_logs("EURUSD", "run-a") == 2
    assert sm.count_audit_logs("EURUSD", "run-b") == 1
    assert sm.count_audit_logs("EURUSD", "run-c") == 0


def test_clear_audit_logs_by_run_id_removes_matching_rows(sm):
    _insert_audit_row(sm, "EURUSD", "threshold_seed")
    _insert_audit_row(sm, "EURUSD", "threshold_seed")
    _insert_audit_row(sm, "EURUSD", "other_run")
    sm.clear_audit_logs_by_run_id("threshold_seed")
    assert sm.count_audit_logs("EURUSD", "threshold_seed") == 0
    assert sm.count_audit_logs("EURUSD", "other_run") == 1


def test_clear_audit_logs_by_run_id_no_op_when_nothing_matches(sm):
    sm.clear_audit_logs_by_run_id("nonexistent")  # must not raise
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_state_manager_queries.py::test_count_audit_logs_returns_correct_count tests/test_state_manager_queries.py::test_clear_audit_logs_by_run_id_removes_matching_rows tests/test_state_manager_queries.py::test_clear_audit_logs_by_run_id_no_op_when_nothing_matches -v 2>&1 | tail -10
```

Expected: 3 failures — `AttributeError: 'StateManager' object has no attribute 'count_audit_logs'`.

- [ ] **Step 3: Implement the two methods in state.py**

Add immediately before `close()` in `src/behemoth/runtime/state.py`:

```python
def count_audit_logs(self, symbol: str, run_id: str) -> int:
    """Return count of audit_logs rows matching (symbol, run_id)."""
    row = self._con.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE symbol = ? AND run_id = ?",
        [symbol.upper(), run_id],
    ).fetchone()
    return int(row[0]) if row else 0

def clear_audit_logs_by_run_id(self, run_id: str) -> None:
    """Delete all audit_logs rows matching run_id (all symbols)."""
    self._con.execute("DELETE FROM audit_logs WHERE run_id = ?", [run_id])
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_state_manager_queries.py -v 2>&1 | tail -10
```

Expected: all 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_state_manager_queries.py src/behemoth/runtime/state.py
git commit -m "feat: add count_audit_logs, clear_audit_logs_by_run_id to StateManager"
```

---

## Task 3: Transactional audit write

**Files:**
- Modify: `src/behemoth/runtime/state.py`
- Modify: `tests/test_state_manager_queries.py`

- [ ] **Step 1: Write failing tests for atomic_audit_replace**

Append to `tests/test_state_manager_queries.py`:

```python
def test_atomic_audit_replace_purges_and_writes(sm):
    # Seed existing rows for (EURUSD, run-x)
    _insert_audit_row(sm, "EURUSD", "run-x")
    _insert_audit_row(sm, "EURUSD", "run-x")
    assert sm.count_audit_logs("EURUSD", "run-x") == 2

    ts = datetime(2026, 2, 1, tzinfo=timezone.utc)
    new_events = [
        (ts, "EURUSD", "cand-new", 0.9, 0.5, "{}", "2026-02", "run-x"),
    ]
    purged = sm.atomic_audit_replace("EURUSD", "run-x", new_events)
    assert purged == 2
    assert sm.count_audit_logs("EURUSD", "run-x") == 1


def test_atomic_audit_replace_rolls_back_on_error(sm):
    _insert_audit_row(sm, "EURUSD", "run-y")

    # Pass a malformed event tuple (wrong column count) to trigger an error
    bad_events = [("not", "enough")]
    with pytest.raises(Exception):
        sm.atomic_audit_replace("EURUSD", "run-y", bad_events)

    # Original row must still be present — rollback happened
    assert sm.count_audit_logs("EURUSD", "run-y") == 1


def test_atomic_audit_replace_returns_zero_when_nothing_purged(sm):
    ts = datetime(2026, 2, 1, tzinfo=timezone.utc)
    events = [(ts, "EURUSD", "cand-001", 0.8, 0.5, "{}", "2026-02", "run-new")]
    purged = sm.atomic_audit_replace("EURUSD", "run-new", events)
    assert purged == 0
    assert sm.count_audit_logs("EURUSD", "run-new") == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_state_manager_queries.py::test_atomic_audit_replace_purges_and_writes tests/test_state_manager_queries.py::test_atomic_audit_replace_rolls_back_on_error tests/test_state_manager_queries.py::test_atomic_audit_replace_returns_zero_when_nothing_purged -v 2>&1 | tail -10
```

Expected: 3 failures — `AttributeError: 'StateManager' object has no attribute 'atomic_audit_replace'`.

- [ ] **Step 3: Implement atomic_audit_replace in state.py**

Add the following import at the top of `state.py` if not already present:

```python
from contextlib import suppress
```

Then add the method immediately before `close()`:

```python
def atomic_audit_replace(
    self, symbol: str, run_id: str, events_batch: list[tuple]
) -> int:
    """Purge existing audit rows for (symbol, run_id) and write events_batch atomically.

    Returns the number of rows purged. Rolls back and re-raises on any error.
    """
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

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_state_manager_queries.py -v 2>&1 | tail -10
```

Expected: all 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_state_manager_queries.py src/behemoth/runtime/state.py
git commit -m "feat: add atomic_audit_replace to StateManager"
```

---

## Task 4: Export warmup bars and checkpoint

**Files:**
- Modify: `src/behemoth/runtime/state.py`
- Modify: `tests/test_state_manager_queries.py`

- [ ] **Step 1: Write failing tests for export_warmup_bars**

Append to `tests/test_state_manager_queries.py`:

```python
def test_export_warmup_bars_writes_parquet_and_returns_row_count(sm, tmp_path):
    import polars as pl

    sm.append_bar(_make_bar("EURUSD", 100, 1, close_bid=1.1000))
    sm.append_bar(_make_bar("EURUSD", 100, 2, close_bid=1.1010))
    sm.append_bar(_make_bar("EURUSD", 200, 3, close_bid=1.2000))  # different bar_ticks, excluded

    out_path = tmp_path / "warmup.parquet"
    count = sm.export_warmup_bars("EURUSD", 100, out_path)

    assert count == 2
    assert out_path.exists()
    df = pl.read_parquet(out_path)
    assert len(df) == 2
    assert "row_id" in df.columns
    assert "close_bid" in df.columns


def test_export_warmup_bars_returns_zero_when_no_rows(sm, tmp_path):
    out_path = tmp_path / "empty.parquet"
    count = sm.export_warmup_bars("NOSYMBOL", 100, out_path)
    assert count == 0
```

- [ ] **Step 2: Write failing test for checkpoint**

Append to `tests/test_state_manager_queries.py`:

```python
def test_checkpoint_does_not_raise(sm):
    sm.append_bar(_make_bar("EURUSD", 100, 1))
    sm.checkpoint()  # must not raise
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
uv run pytest tests/test_state_manager_queries.py::test_export_warmup_bars_writes_parquet_and_returns_row_count tests/test_state_manager_queries.py::test_export_warmup_bars_returns_zero_when_no_rows tests/test_state_manager_queries.py::test_checkpoint_does_not_raise -v 2>&1 | tail -10
```

Expected: 3 failures — `AttributeError`.

- [ ] **Step 4: Implement export_warmup_bars and checkpoint in state.py**

Add immediately before `close()` in `src/behemoth/runtime/state.py`:

```python
def export_warmup_bars(self, symbol: str, bar_ticks: int, path: Path) -> int:
    """Write tick_bars rows for (symbol, bar_ticks) to a Parquet file at path.

    Returns the number of rows written. The caller owns the file lifecycle.
    StateManager never imports polars or pandas — DuckDB writes the Parquet directly.
    Returns 0 without creating the file when there are no matching rows.
    """
    row = self._con.execute(
        "SELECT COUNT(*) FROM tick_bars WHERE symbol = ? AND bar_ticks = ?",
        [symbol.upper(), bar_ticks],
    ).fetchone()
    count = int(row[0]) if row else 0
    if count == 0:
        return 0
    self._con.execute(
        f"""
        COPY (
            SELECT row_id, ts, close_ts, open_bid, high_bid, low_bid, close_bid,
                   spread, tick_volume, hl_first, hl_pos_frac, high_ask, close_ask
            FROM tick_bars
            WHERE symbol = ? AND bar_ticks = ?
            ORDER BY row_id
        ) TO '{path}' (FORMAT PARQUET)
        """,
        [symbol.upper(), bar_ticks],
    )
    return count

def checkpoint(self) -> None:
    """Force DuckDB to flush the WAL to the on-disk database file."""
    self._con.execute("CHECKPOINT")
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
uv run pytest tests/test_state_manager_queries.py -v 2>&1 | tail -10
```

Expected: all 15 tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_state_manager_queries.py src/behemoth/runtime/state.py
git commit -m "feat: add export_warmup_bars, checkpoint to StateManager"
```

---

## Task 5: Replace server.py call sites

**Files:**
- Modify: `src/behemoth/api/server.py`

Replace each of the 11 raw `_con.execute` call sites one by one. After all replacements, run the full test suite.

- [ ] **Step 1: Replace line 604 — entry price lookup in _build_open_positions_summary**

Find (around line 604):
```python
row = state._con.execute(
    "SELECT entry_price FROM trades WHERE reservation_id = ? AND status = 'OPEN'",
    [r["reservation_id"]],
).fetchone()
if row:
    entry_price = float(row[0])
```

Replace with:
```python
entry_price = state.get_open_trade_entry_price(r["reservation_id"])
```

- [ ] **Step 2: Replace line 662 — bars elapsed in _build_open_positions_summary**

Find (around line 662):
```python
current_row_id = state._con.execute(
    "SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?", [sym.upper()]
).fetchone()
current_bar = int(current_row_id[0]) if current_row_id and current_row_id[0] else 0
```

Replace with:
```python
current_bar = state.get_latest_bar_id(sym)
```

- [ ] **Step 3: Replace line 1117 — clear seed logs in _load_seed_files**

Find (around line 1117):
```python
_state._con.execute("DELETE FROM audit_logs WHERE run_id = 'threshold_seed'")
```

Replace with:
```python
_state.clear_audit_logs_by_run_id("threshold_seed")
```

- [ ] **Step 4: Replace line 1165 — latest tick snapshot in _latest_tick_price_snapshot**

Find the full `_latest_tick_price_snapshot` function (around line 1162):
```python
def _latest_tick_price_snapshot(sym: str) -> dict[str, Any] | None:
    if _state is None:
        return None
    row = _state._con.execute(
        """
        SELECT close_bid, close_ts
        FROM tick_bars
        WHERE symbol = ?
        ORDER BY row_id DESC
        LIMIT 1
        """,
        [sym.upper()],
    ).fetchone()
    if not row or row[0] is None:
        return None
    close_ts = row[1]
    if isinstance(close_ts, datetime):
        if close_ts.tzinfo is None:
            close_ts = close_ts.replace(tzinfo=timezone.utc)
        else:
            close_ts = close_ts.astimezone(timezone.utc)
    return {
        "symbol": sym.upper(),
        "price": float(row[0]),
        "close_ts": close_ts,
    }
```

Replace with:
```python
def _latest_tick_price_snapshot(sym: str) -> dict[str, Any] | None:
    if _state is None:
        return None
    result = _state.get_latest_tick_snapshot(sym)
    if result is None:
        return None
    price, close_ts = result
    return {"symbol": sym.upper(), "price": price, "close_ts": close_ts}
```

- [ ] **Step 5: Replace line 3412 — warmup bars fetch**

Add `import tempfile` to the imports at the top of `server.py` if not already present.

Find (around line 3406):
```python
bars_by_ticks: dict[int, pd.DataFrame] = {}
for cand in contract.candidates:
    bar_ticks = int(cand.bar_ticks)
    if bar_ticks in bars_by_ticks:
        continue
    bars_df = _state._con.execute(
        """
        SELECT
            row_id,
            ts,
            close_ts,
            open_bid,
            high_bid,
            low_bid,
            close_bid,
            spread,
            tick_volume,
            hl_first,
            hl_pos_frac,
            high_ask,
            close_ask
        FROM tick_bars
        WHERE symbol = ? AND bar_ticks = ?
        ORDER BY row_id
        """,
        [sym, bar_ticks],
    ).fetchdf()
    if len(bars_df) < warmup_needed:
        return {
            "ok": True,
            "symbol": sym,
            "audit_events_purged": 0,
            "audit_events_written": 0,
            "skipped_reason": f"insufficient_bars:{len(bars_df)}<{warmup_needed}",
            "stats": {},
        }
    for col in ("ts", "close_ts"):
        if col in bars_df.columns:
            ts_series = pd.to_datetime(bars_df[col], utc=True)
            bars_df[col] = ts_series
    bars_by_ticks[bar_ticks] = bars_df
```

Replace with:
```python
bars_by_ticks: dict[int, pd.DataFrame] = {}
for cand in contract.candidates:
    bar_ticks = int(cand.bar_ticks)
    if bar_ticks in bars_by_ticks:
        continue
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        tmp_path = Path(f.name)
    # delete=False: NamedTemporaryFile with delete=True closes+deletes before caller can read
    try:
        _state.export_warmup_bars(sym, bar_ticks, tmp_path)
        bars_df = pd.read_parquet(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    if len(bars_df) < warmup_needed:
        return {
            "ok": True,
            "symbol": sym,
            "audit_events_purged": 0,
            "audit_events_written": 0,
            "skipped_reason": f"insufficient_bars:{len(bars_df)}<{warmup_needed}",
            "stats": {},
        }
    for col in ("ts", "close_ts"):
        if col in bars_df.columns:
            bars_df[col] = pd.to_datetime(bars_df[col], utc=True)
    bars_by_ticks[bar_ticks] = bars_df
```

The downstream warmup code (`compute_feature_matrix_from_bars`, `.loc`, `.iloc`) all uses pandas — keep the DataFrame as pandas for now. The `export_warmup_bars` method still provides the seam benefit (SQL gone from server.py); a full Polars migration of the warmup path is a separate future step.

- [ ] **Step 6: Replace line 3536 — count audit rows in predict_warmup**

Find (around line 3536):
```python
existing_rows = _state._con.execute(
    "SELECT COUNT(*) FROM audit_logs WHERE symbol = ? AND run_id = ?",
    [sym, run_id],
).fetchone()[0]
```

Replace with:
```python
existing_rows = _state.count_audit_logs(sym, run_id)
```

- [ ] **Step 7: Replace lines 3557–3563 — transaction block in predict_warmup**

Find (around line 3557):
```python
audit_events_purged = 0
try:
    _state._con.execute("BEGIN TRANSACTION")
    audit_events_purged = _state.purge_audit_events(symbol=sym, run_id=run_id)
    _state.log_audit_event_batch(events_batch)
    _state._con.execute("COMMIT")
except Exception:
    with suppress(Exception):
        _state._con.execute("ROLLBACK")
    raise
```

Replace with:
```python
audit_events_purged = _state.atomic_audit_replace(sym, run_id, events_batch)
```

- [ ] **Step 8: Replace line 3664 — checkpoint endpoint**

Find (around line 3664):
```python
_state._con.execute("CHECKPOINT")
```

Replace with:
```python
_state.checkpoint()
```

- [ ] **Step 9: Replace line 3933 — MAX(row_id) in trades/touch endpoint**

Find (around line 3933):
```python
res = _state._con.execute("SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?", [sym]).fetchone()
touch_bar_id = res[0] if res and res[0] is not None else 0
```

Replace with:
```python
touch_bar_id = _state.get_latest_bar_id(sym)
```

- [ ] **Step 10: Verify no _con.execute leaks remain (excluding BarrierManager)**

```bash
grep -n "_state\._con\|state\._con" src/behemoth/api/server.py
```

Expected output: only the `BarrierManager(con=_state._con)` line (line ~766). Everything else should be gone.

- [ ] **Step 11: Run the full test suite**

```bash
uv run pytest -q 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 12: Commit**

```bash
git add src/behemoth/api/server.py
git commit -m "fix: replace raw _con.execute leaks in server.py with StateManager methods"
```

---

## Task 6: Final Verification

**Files:** none

- [ ] **Step 1: Confirm no _con.execute leaks remain outside BarrierManager**

```bash
grep -n "_con\.execute\|_state\._con" src/behemoth/api/server.py
```

Expected: only `BarrierManager(con=_state._con)` on its one line.

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest -q 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 3: Confirm all 8 new methods exist on StateManager**

```bash
grep -n "def get_open_trade_entry_price\|def get_latest_bar_id\|def get_latest_tick_snapshot\|def clear_audit_logs_by_run_id\|def count_audit_logs\|def atomic_audit_replace\|def export_warmup_bars\|def checkpoint" src/behemoth/runtime/state.py
```

Expected: 8 matches.

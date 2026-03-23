# State Manager Bar Cache Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-predict DuckDB round-trips in `StateManager` with an in-memory `deque`-backed bar cache, eliminating DuckDB read overhead from the predict hot path.

**Architecture:** Add a `_bar_cache: dict[str, deque[_BarRow]]` (keyed `"SYM_100"`, maxlen=600) and a `_latest_close_ts: dict[str, datetime]` to `StateManager`. `append_bar()` writes to both DuckDB (persistence) and the in-memory cache. `compute_features()`, `compute_regime_quantiles()`, `bar_count()`, and `get_latest_close_ts()` all read from the cache — zero DuckDB reads on the predict hot path. Feature math delegates unchanged to `compute_features_from_bars()`, guaranteeing identical results. On startup with a persistent DB, the cache is hydrated from existing `tick_bars` rows.

**Tech Stack:** Python `collections.deque`, `typing.NamedTuple`, `pandas.DataFrame`, existing `compute_features_from_bars()` / `compute_regime_quantiles_from_bars()` — no new dependencies.

---

## Background

### Why this matters

`compute_features()` and `compute_regime_quantiles()` are called on every `/predict` request. They currently:
1. Run `bar_count()` → `SELECT COUNT(*) FROM tick_bars WHERE symbol=? AND bar_ticks=?` (DuckDB)
2. Run `_SELECT_SQL` → `SELECT … LIMIT 600` + `fetchdf()` (DuckDB → Python object allocation)
3. Run pandas rolling on the 600-row DataFrame

The DuckDB round-trip (steps 1–2) is unnecessary: `append_bar()` already has this data. With a `deque`, steps 1–2 become O(1) Python dict/deque lookups, and the pandas rolling in step 3 operates on a Python-native structure (`pd.DataFrame.from_records`) instead of a DuckDB result.

`get_latest_close_ts()` and `bar_count()` are called from the metrics collector, health endpoint, predict response body, and backfill endpoint — all on the hot path. The same cache eliminates their DuckDB queries too.

### Production alignment

In a live trading deployment, bar state is maintained in memory as ticks arrive. The in-memory cache is the first step toward that pattern: feature decisions pull from RAM, not from DuckDB reads.

### What is NOT changing

- DuckDB writes in `append_bar()` are unchanged — persistence is preserved.
- `compute_features_from_bars()` and `compute_regime_quantiles_from_bars()` are unchanged — they remain the single source of truth for feature math.
- The `tick_bars` DuckDB table continues to exist and be pruned as before.

---

## File Structure

| File | Change | Role |
|------|--------|------|
| `src/behemoth/runtime/state.py` | Modify | Add `_BarRow`, `_bar_cache`, `_latest_close_ts`; update 5 methods |
| `tests/test_state_bar_cache.py` | Create | Correctness and hydration tests |

---

## Task 1: Write failing tests

**Files:**
- Create: `tests/test_state_bar_cache.py`

- [ ] **Step 1: Write test skeleton**

```python
"""Tests for StateManager in-memory bar cache.

These tests verify that the cache-backed versions of bar_count(),
get_latest_close_ts(), compute_features(), and compute_regime_quantiles()
produce identical results to the DuckDB-backed versions before the cache
was introduced, and that the cache is correctly hydrated from a persistent
DuckDB store on restart.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone

import pandas as pd
import pytest

from src.behemoth.core.features import FeatureConfig, compute_features_from_bars
from src.behemoth.core.schemas import IncomingTickBar
from src.behemoth.runtime.state import StateManager


def _make_bar(
    i: int,
    symbol: str = "EURUSD",
    bar_ticks: int = 100,
    *,
    base_ts: datetime | None = None,
) -> IncomingTickBar:
    """Generate a synthetic bar with realistic-looking OHLC values."""
    if base_ts is None:
        base_ts = datetime(2025, 7, 7, 0, 0, 0, tzinfo=timezone.utc)
    from datetime import timedelta

    open_price = 1.0800 + (i % 50) * 0.0001
    close_price = open_price + 0.0002 * (1 if i % 3 else -1)
    high_price = max(open_price, close_price) + 0.0001
    low_price = min(open_price, close_price) - 0.0001
    spread = 0.00010 + (i % 5) * 0.00001
    tick_volume = 100.0 + i % 20

    ts = base_ts + timedelta(minutes=i * 3)
    close_ts = ts + timedelta(minutes=3)

    return IncomingTickBar(
        symbol=symbol,
        bar_ticks=bar_ticks,
        timestamp=ts,
        close_ts=close_ts,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        spread=spread,
        tick_volume=tick_volume,
        hl_first=1 if i % 2 else 0,
        hl_pos_frac=float(i % 10) / 10.0,
    )
```

- [ ] **Step 2: Write test for `bar_count` correctness**

```python
def test_bar_count_returns_correct_count() -> None:
    """bar_count() returns the number of bars appended, not exceeding 600."""
    sm = StateManager()
    assert sm.bar_count("EURUSD", 100) == 0

    for i in range(50):
        sm.append_bar(_make_bar(i))

    assert sm.bar_count("EURUSD", 100) == 50
```

- [ ] **Step 3: Write test for `get_latest_close_ts` correctness**

```python
def test_get_latest_close_ts_returns_most_recent() -> None:
    """get_latest_close_ts() returns the close_ts of the last appended bar."""
    sm = StateManager()
    assert sm.get_latest_close_ts("EURUSD") is None

    bars = [_make_bar(i) for i in range(10)]
    for bar in bars:
        sm.append_bar(bar)

    expected = bars[-1].close_ts
    result = sm.get_latest_close_ts("EURUSD")
    assert result is not None
    # Compare naive UTC equivalents (tzinfo may differ in representation)
    assert result.replace(tzinfo=None) == expected.replace(tzinfo=None)
```

- [ ] **Step 4: Write test for `compute_features` matching direct call**

```python
def test_compute_features_matches_direct_compute() -> None:
    """compute_features() returns same result as compute_features_from_bars()
    called directly on the same bar data."""
    sm = StateManager()
    N = 300  # more than full_warmup_bars=289

    bars = [_make_bar(i) for i in range(N)]
    for bar in bars:
        sm.append_bar(bar)

    result = sm.compute_features("EURUSD", bar_ticks=100, horizon=10, barrier_pips=20.0)
    assert result is not None, "Expected features after 300 bars"

    # Build the same DataFrame that the old DuckDB path would have built
    rows = [
        {
            "ts": b.timestamp,
            "close_ts": b.close_ts,
            "open_price": b.open,
            "high_price": b.high,
            "low_price": b.low,
            "close_price": b.close,
            "spread": b.spread,
            "tick_volume": b.tick_volume,
            "hl_first": b.hl_first,
            "hl_pos_frac": b.hl_pos_frac,
        }
        for b in bars[-300:]  # last 300 (all of them here, cache holds up to 600)
    ]
    df = pd.DataFrame(rows)
    expected = compute_features_from_bars(
        df, symbol="EURUSD", bar_ticks=100, horizon=10, barrier_pips=20.0
    )
    assert expected is not None

    assert abs(result.cost_est_pips - expected.cost_est_pips) < 1e-9
    assert abs(result.range_pips - expected.range_pips) < 1e-9
    assert abs(result.ret_z - expected.ret_z) < 1e-9
```

- [ ] **Step 5: Write test for insufficient warmup**

```python
def test_compute_features_returns_none_before_warmup() -> None:
    """compute_features() returns None until full_warmup_bars (289) bars are present."""
    sm = StateManager()

    for i in range(288):
        sm.append_bar(_make_bar(i))
    assert sm.compute_features("EURUSD", bar_ticks=100, horizon=10, barrier_pips=20.0) is None

    sm.append_bar(_make_bar(288))  # 289th bar
    assert sm.compute_features("EURUSD", bar_ticks=100, horizon=10, barrier_pips=20.0) is not None
```

- [ ] **Step 6: Write test for cache hydration on restart**

```python
def test_cache_hydrated_from_persistent_db() -> None:
    """On restart, the cache is populated from the existing DuckDB rows,
    so compute_features() works immediately without re-feeding bars."""
    N = 300
    bars = [_make_bar(i) for i in range(N)]

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # First session: append bars
        sm1 = StateManager(persist_path=db_path)
        for bar in bars:
            sm1.append_bar(bar)

        result1 = sm1.compute_features("EURUSD", bar_ticks=100, horizon=10, barrier_pips=20.0)
        assert result1 is not None

        # Second session: fresh StateManager, same DB
        sm2 = StateManager(persist_path=db_path)
        result2 = sm2.compute_features("EURUSD", bar_ticks=100, horizon=10, barrier_pips=20.0)
        assert result2 is not None

        assert abs(result1.cost_est_pips - result2.cost_est_pips) < 1e-9
        assert abs(result1.range_pips - result2.range_pips) < 1e-9
    finally:
        import os
        os.unlink(db_path)
```

- [ ] **Step 7: Write test for deque maxlen=600**

```python
def test_cache_does_not_exceed_600_bars() -> None:
    """The cache holds at most 600 bars per (symbol, bar_ticks)."""
    sm = StateManager()
    for i in range(700):
        sm.append_bar(_make_bar(i))

    # bar_count() reflects DuckDB pruning (keeps 600), but cache is also capped at 600
    count = sm.bar_count("EURUSD", 100)
    assert count <= 600
```

- [ ] **Step 8: Run tests — expect ALL to fail (cache not yet implemented)**

```bash
uv run pytest tests/test_state_bar_cache.py -v
```

Expected: multiple FAIL or ERROR. The new tests reference cache behaviour that doesn't exist yet.

---

## Task 2: Implement the bar cache

**Files:**
- Modify: `src/behemoth/runtime/state.py`

- [ ] **Step 1: Add imports and `_BarRow` NamedTuple**

After the existing imports block at the top of `state.py` (after the `import duckdb` line), add:

```python
from collections import deque
from typing import NamedTuple


class _BarRow(NamedTuple):
    """Lightweight in-memory representation of one tick bar (matches DuckDB column names)."""

    ts: datetime
    close_ts: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    spread: float
    tick_volume: float
    hl_first: float
    hl_pos_frac: float
```

- [ ] **Step 2: Run tests — still fail (StateManager not updated yet)**

```bash
uv run pytest tests/test_state_bar_cache.py -v
```

Expected: FAIL on all tests (StateManager still uses DuckDB for reads).

- [ ] **Step 3: Add cache fields to `StateManager.__init__`**

In `StateManager.__init__`, after the `self._row_counters: dict[str, int] = {}` line, add:

```python
        # In-memory bar cache: eliminates DuckDB reads from the predict hot path.
        # Keyed by "{SYM}_{bar_ticks}", maxlen=600 matches _SELECT_SQL LIMIT 600.
        self._bar_cache: dict[str, deque[_BarRow]] = {}
        # Latest close_ts per symbol (across all bar_ticks) for get_latest_close_ts().
        self._latest_close_ts: dict[str, datetime | None] = {}
```

Then, in the startup hydration block (the `for r in res:` loop that reads `MAX(row_id)` from DuckDB), extend it to also populate the cache. Replace:

```python
        res = self._con.execute(
            "SELECT symbol, bar_ticks, MAX(row_id) FROM tick_bars GROUP BY symbol, bar_ticks"
        ).fetchall()
        for r in res:
            if r[2] is not None:
                self._row_counters[f"{r[0].upper()}_{r[1]}"] = int(r[2]) + 1
```

with:

```python
        res = self._con.execute(
            "SELECT symbol, bar_ticks, MAX(row_id) FROM tick_bars GROUP BY symbol, bar_ticks"
        ).fetchall()
        for r in res:
            sym_upper = r[0].upper()
            if r[2] is not None:
                self._row_counters[f"{sym_upper}_{r[1]}"] = int(r[2]) + 1
            self._hydrate_cache(sym_upper, int(r[1]))
```

- [ ] **Step 4: Add `_hydrate_cache` method**

Add this private method to `StateManager` (after `__init__`, before `_ensure_runtime_schema`):

```python
    def _hydrate_cache(self, symbol: str, bar_ticks: int) -> None:
        """Populate the in-memory bar cache from existing DuckDB rows (called on startup)."""
        key = f"{symbol}_{bar_ticks}"
        rows = self._con.execute(
            """
            SELECT ts, close_ts, open_price, high_price, low_price,
                   close_price, spread, tick_volume, hl_first, hl_pos_frac
            FROM (
                SELECT ts, close_ts, open_price, high_price, low_price,
                       close_price, spread, tick_volume, hl_first, hl_pos_frac, row_id
                FROM tick_bars
                WHERE symbol = ? AND bar_ticks = ?
                ORDER BY row_id DESC
                LIMIT 600
            ) sub
            ORDER BY row_id ASC
            """,
            [symbol, bar_ticks],
        ).fetchall()

        cache: deque[_BarRow] = deque(maxlen=600)
        for row in rows:
            cache.append(_BarRow(*row))
            # Track latest close_ts across all bar_ticks for this symbol
            close_ts = row[1]
            if close_ts is not None:
                existing = self._latest_close_ts.get(symbol)
                if existing is None or close_ts > existing:
                    self._latest_close_ts[symbol] = close_ts
        self._bar_cache[key] = cache
```

- [ ] **Step 5: Update `append_bar()` to push to cache**

In the `append_bar()` method, after the line `self._row_counters[key] = idx + 1`, add:

```python
        # Update in-memory cache (eliminates DuckDB reads on predict hot path)
        cache = self._bar_cache.get(key)
        if cache is None:
            cache = deque(maxlen=600)
            self._bar_cache[key] = cache
        cache.append(
            _BarRow(
                ts=bar.timestamp,
                close_ts=bar.close_ts,
                open_price=bar.open,
                high_price=bar.high,
                low_price=bar.low,
                close_price=bar.close,
                spread=bar.spread,
                tick_volume=bar.tick_volume,
                hl_first=bar.hl_first,
                hl_pos_frac=bar.hl_pos_frac,
            )
        )
        existing_ts = self._latest_close_ts.get(sym)
        if existing_ts is None or bar.close_ts > existing_ts:
            self._latest_close_ts[sym] = bar.close_ts
```

Note: `sym` is already defined as `bar.symbol.upper()` earlier in `append_bar()` (line 266 in state.py) — the inserted code uses it directly.

- [ ] **Step 6: Update `bar_count()` to use cache**

Replace:

```python
    def bar_count(self, symbol: str, bar_ticks: int) -> int:
        """Return the number of bars currently stored for a symbol + horizon."""
        r = self._con.execute(
            "SELECT COUNT(*) FROM tick_bars WHERE symbol = ? AND bar_ticks = ?",
            [symbol.upper(), bar_ticks],
        ).fetchone()
        return int(r[0]) if r else 0
```

with:

```python
    def bar_count(self, symbol: str, bar_ticks: int) -> int:
        """Return the number of bars currently stored for a symbol + horizon."""
        cache = self._bar_cache.get(f"{symbol.upper()}_{bar_ticks}")
        return len(cache) if cache is not None else 0
```

- [ ] **Step 7: Update `get_latest_close_ts()` to use cache**

Replace:

```python
    def get_latest_close_ts(self, symbol: str) -> datetime | None:
        """Return the close_ts of the most recent bar."""
        r = self._con.execute(
            "SELECT close_ts FROM tick_bars WHERE symbol = ? ORDER BY row_id DESC LIMIT 1",
            [symbol.upper()],
        ).fetchone()
        return r[0] if r else None
```

with:

```python
    def get_latest_close_ts(self, symbol: str) -> datetime | None:
        """Return the close_ts of the most recent bar."""
        return self._latest_close_ts.get(symbol.upper())
```

- [ ] **Step 8: Update `compute_features()` to use cache**

Replace:

```python
    def compute_features(
        self,
        symbol: str,
        bar_ticks: int,
        horizon: int,
        barrier_pips: float,
    ) -> ModelFeatures | None:
        ...
        sym = symbol.upper()
        n = self.bar_count(sym, bar_ticks)
        if n < self._cfg.full_warmup_bars:
            return None

        df = self._con.execute(_SELECT_SQL, [sym, bar_ticks]).fetchdf()

        return compute_features_from_bars(
            df,
            symbol=sym,
            bar_ticks=bar_ticks,
            horizon=horizon,
            barrier_pips=barrier_pips,
            cfg=self._cfg,
        )
```

with:

```python
    def compute_features(
        self,
        symbol: str,
        bar_ticks: int,
        horizon: int,
        barrier_pips: float,
    ) -> ModelFeatures | None:
        """Compute the 16-parameter feature vector for the latest bar.

        Delegates all rolling-window math to the canonical builder in
        ``src.behemoth.core.features.compute_features_from_bars()``.

        Returns None if the buffer has insufficient warmup history.
        """
        sym = symbol.upper()
        cache = self._bar_cache.get(f"{sym}_{bar_ticks}")
        if cache is None or len(cache) < self._cfg.full_warmup_bars:
            return None

        df = pd.DataFrame(list(cache), columns=_BarRow._fields)
        return compute_features_from_bars(
            df,
            symbol=sym,
            bar_ticks=bar_ticks,
            horizon=horizon,
            barrier_pips=barrier_pips,
            cfg=self._cfg,
        )
```

- [ ] **Step 9: Update `compute_regime_quantiles()` to use cache**

Replace the DuckDB path identically — same pattern as Step 8:

```python
    def compute_regime_quantiles(self, symbol: str, bar_ticks: int) -> dict[str, float]:
        """Compute runtime regime quantiles from the recent bar buffer."""
        sym = symbol.upper()
        cache = self._bar_cache.get(f"{sym}_{bar_ticks}")
        if cache is None or len(cache) < self._cfg.full_warmup_bars:
            return {}

        df = pd.DataFrame(list(cache), columns=_BarRow._fields)
        return compute_regime_quantiles_from_bars(df, symbol=sym, cfg=self._cfg)
```

- [ ] **Step 10: Add `import pandas as pd` to `state.py` imports**

Add `import pandas as pd` to the imports at the top of `state.py` (it's a direct dependency now).

- [ ] **Step 11: Run tests — expect all to pass**

```bash
uv run pytest tests/test_state_bar_cache.py -v
```

Expected output:
```
tests/test_state_bar_cache.py::test_bar_count_returns_correct_count PASSED
tests/test_state_bar_cache.py::test_get_latest_close_ts_returns_most_recent PASSED
tests/test_state_bar_cache.py::test_compute_features_matches_direct_compute PASSED
tests/test_state_bar_cache.py::test_compute_features_returns_none_before_warmup PASSED
tests/test_state_bar_cache.py::test_cache_hydrated_from_persistent_db PASSED
tests/test_state_bar_cache.py::test_cache_does_not_exceed_600_bars PASSED

6 passed in ...
```

If `test_compute_features_matches_direct_compute` fails with floating-point differences > 1e-9, check whether the DataFrame column types differ between the direct construction and the DuckDB path — ensure `_BarRow` field values are cast to `float` before append.

- [ ] **Step 12: Run the full test suite**

```bash
uv run pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 13: Commit**

```bash
git add src/behemoth/runtime/state.py tests/test_state_bar_cache.py
git commit -m "perf: replace DuckDB reads with in-memory bar cache in StateManager

compute_features(), compute_regime_quantiles(), bar_count(), and
get_latest_close_ts() now read from a deque[_BarRow] maintained
alongside DuckDB writes. Eliminates 4 DuckDB SELECT round-trips per
predict call. Feature math delegates unchanged to compute_features_from_bars()
— identical results guaranteed.

Cache is hydrated from tick_bars on startup for restart recovery."
```

---

## Verification

After implementing, run the spotlight pipeline to confirm correctness and observe the speed improvement:

```bash
make local-jforex-parity-spotlight
```

EURUSD (20 events, 116,400 ticks) should still complete in ~27 seconds. GBPUSD (104 events, 181,500 ticks) should complete faster and without the 60-second timeout — the DuckDB read overhead is eliminated on the predict path.

If GBPUSD still times out, the bottleneck is in the `/ticks/batch` write path or tick aggregation (not feature reads) and requires separate investigation.

---

## Notes on `_SELECT_SQL`

After this change, `_SELECT_SQL` is only used if a caller bypasses `compute_features()` and `compute_regime_quantiles()` directly. It can remain in the file as a fallback or be removed in a separate cleanup. Do NOT remove it in this PR — leave it for now.

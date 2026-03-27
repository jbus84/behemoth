# Tick Vault Weekend Gap Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `scripts/download_tick_vault_data.py` treat the normal Dukascopy weekend closure as expected, stop current-month Friday-after-close overfetching, and clean up clearly stale downloader lockfiles.

**Architecture:** Keep the fix inside `scripts/download_tick_vault_data.py`. Add a small DST-aware session helper built around the New York `17:00` Friday close / Sunday reopen convention in `America/New_York`, use it to classify gaps and fetchable time ranges, then add focused pytest coverage with synthetic parquet fixtures and lockfile/process monkeypatching.

**Tech Stack:** Python 3.12, `zoneinfo`, `pandas`, `numpy`, `pytest`, parquet fixtures in `tmp_path`

---

## File Structure

- Modify: `scripts/download_tick_vault_data.py`
  - Add DST-aware session helpers.
  - Update gap classification to ignore scheduled weekend closures.
  - Reorder current-month logic so append decisions are based on the effective session end.
  - Add conservative stale-lock cleanup before the downloader creates a new lock.
- Create: `tests/test_download_tick_vault_data.py`
  - Add focused unit tests for session boundary classification, gap detection, current-month refill scheduling, and stale-lock cleanup.

### Task 1: Add DST-Aware Session Helpers

**Files:**
- Modify: `scripts/download_tick_vault_data.py`
- Test: `tests/test_download_tick_vault_data.py`

- [ ] **Step 1: Write the failing session-boundary tests**

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts.download_tick_vault_data import (
    get_session_bounds_utc,
    is_expected_weekend_gap,
    is_fx_market_open,
)


def test_is_fx_market_open_handles_winter_friday_close() -> None:
    assert is_fx_market_open(datetime(2026, 1, 2, 21, 30, tzinfo=UTC)) is True
    assert is_fx_market_open(datetime(2026, 1, 2, 22, 0, tzinfo=UTC)) is False
    assert is_fx_market_open(datetime(2026, 1, 4, 21, 59, tzinfo=UTC)) is False
    assert is_fx_market_open(datetime(2026, 1, 4, 22, 0, tzinfo=UTC)) is True


def test_is_fx_market_open_handles_dst_friday_close() -> None:
    assert is_fx_market_open(datetime(2025, 10, 3, 20, 30, tzinfo=UTC)) is True
    assert is_fx_market_open(datetime(2025, 10, 3, 21, 0, tzinfo=UTC)) is False
    assert is_fx_market_open(datetime(2025, 10, 5, 20, 59, tzinfo=UTC)) is False
    assert is_fx_market_open(datetime(2025, 10, 5, 21, 0, tzinfo=UTC)) is True


def test_get_session_bounds_utc_matches_new_york_close_reopen() -> None:
    close_utc, reopen_utc = get_session_bounds_utc(datetime(2025, 10, 3, 12, 0, tzinfo=UTC))
    assert close_utc.isoformat() == "2025-10-03T21:00:00+00:00"
    assert reopen_utc.isoformat() == "2025-10-05T21:00:00+00:00"


def test_is_expected_weekend_gap_matches_observed_gap() -> None:
    prev_ts = datetime(2025, 10, 3, 20, 59, 59, 574000, tzinfo=UTC)
    next_ts = datetime(2025, 10, 5, 21, 0, 42, 115000, tzinfo=UTC)
    assert is_expected_weekend_gap(prev_ts, next_ts) is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_download_tick_vault_data.py -k "market_open or session_bounds or weekend_gap"`

Expected: `ImportError` or `AttributeError` for the new helper names.

- [ ] **Step 3: Write the minimal session helper implementation**

```python
from zoneinfo import ZoneInfo


NEW_YORK_TZ = ZoneInfo("America/New_York")


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _friday_close_for_week(dt: datetime) -> datetime:
    dt_utc = _normalize_utc(dt)
    dt_ny = dt_utc.astimezone(NEW_YORK_TZ)
    days_to_friday = 4 - dt_ny.weekday()
    target = (dt_ny + relativedelta(days=days_to_friday)).replace(
        hour=17,
        minute=0,
        second=0,
        microsecond=0,
    )
    return target.astimezone(UTC)


def get_session_bounds_utc(dt: datetime) -> tuple[datetime, datetime]:
    close_utc = _friday_close_for_week(dt)
    reopen_utc = (close_utc.astimezone(NEW_YORK_TZ) + relativedelta(days=2)).astimezone(UTC)
    return close_utc, reopen_utc


def is_fx_market_open(dt: datetime) -> bool:
    dt_utc = _normalize_utc(dt)
    close_utc, reopen_utc = get_session_bounds_utc(dt_utc)
    return not (close_utc <= dt_utc < reopen_utc)


def is_expected_weekend_gap(prev_ts: datetime, next_ts: datetime) -> bool:
    prev_utc = _normalize_utc(prev_ts)
    next_utc = _normalize_utc(next_ts)
    close_utc, reopen_utc = get_session_bounds_utc(prev_utc)
    return prev_utc < close_utc <= reopen_utc <= next_utc
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_download_tick_vault_data.py -k "market_open or session_bounds or weekend_gap"`

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/download_tick_vault_data.py tests/test_download_tick_vault_data.py
git commit -m "fix: add dst-aware tick vault session boundaries"
```

### Task 2: Make Gap Detection Ignore Scheduled Weekend Closures

**Files:**
- Modify: `scripts/download_tick_vault_data.py`
- Test: `tests/test_download_tick_vault_data.py`

- [ ] **Step 1: Write the failing gap-detection tests**

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from scripts.download_tick_vault_data import find_first_market_gap


def _write_timestamp_only_parquet(path: Path, timestamps: list[datetime]) -> None:
    pd.DataFrame({"timestamp": pd.to_datetime(timestamps, utc=True)}).to_parquet(path, index=False)


def test_find_first_market_gap_ignores_expected_weekend_gap(tmp_path: Path) -> None:
    path = tmp_path / "eurusd.parquet"
    _write_timestamp_only_parquet(
        path,
        [
            datetime(2025, 10, 3, 20, 59, 59, 574000, tzinfo=UTC),
            datetime(2025, 10, 5, 21, 0, 42, 115000, tzinfo=UTC),
        ],
    )
    assert find_first_market_gap(path) is None


def test_find_first_market_gap_returns_weekday_gap(tmp_path: Path) -> None:
    path = tmp_path / "eurusd.parquet"
    _write_timestamp_only_parquet(
        path,
        [
            datetime(2025, 10, 6, 10, 0, 0, tzinfo=UTC),
            datetime(2025, 10, 6, 13, 30, 0, tzinfo=UTC),
        ],
    )
    assert find_first_market_gap(path) == datetime(2025, 10, 6, 10, 0, 0, tzinfo=UTC)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_download_tick_vault_data.py -k "find_first_market_gap"`

Expected: the weekend-gap test fails because the current implementation returns the Friday close timestamp.

- [ ] **Step 3: Update gap classification to use both sides of the gap**

```python
def find_first_market_gap(path: Path) -> datetime | None:
    import pandas as pd

    try:
        df = pd.read_parquet(path, columns=["timestamp"])
        if df.empty:
            return None

        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["diff"] = df["timestamp"].diff().dt.total_seconds()
        gaps = df[df["diff"] > 7200].copy()
        if gaps.empty:
            return None

        for idx in gaps.index:
            prev_ts = df.loc[idx - 1, "timestamp"].to_pydatetime()
            next_ts = df.loc[idx, "timestamp"].to_pydatetime()
            if is_expected_weekend_gap(prev_ts, next_ts):
                continue
            if is_fx_market_open(prev_ts) or is_fx_market_open(next_ts):
                return prev_ts
        return None
    except Exception:
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_download_tick_vault_data.py -k "find_first_market_gap"`

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/download_tick_vault_data.py tests/test_download_tick_vault_data.py
git commit -m "fix: ignore scheduled weekend closures in gap detection"
```

### Task 3: Rework Current-Month Refill Scheduling Around Fetchable Session End

**Files:**
- Modify: `scripts/download_tick_vault_data.py`
- Test: `tests/test_download_tick_vault_data.py`

- [ ] **Step 1: Write the failing current-month scheduling tests**

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from scripts.download_tick_vault_data import get_missing_months


def _write_tick_parquet(path: Path, timestamps: list[datetime]) -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, utc=True),
            "bid": [1.1] * len(timestamps),
            "ask": [1.1001] * len(timestamps),
        }
    )
    frame.to_parquet(path, index=False)


def test_get_missing_months_does_not_refill_after_friday_close(monkeypatch, tmp_path: Path) -> None:
    out_dir = tmp_path / "dukascopy_ticks"
    symbol_dir = out_dir / "EURUSD"
    symbol_dir.mkdir(parents=True, exist_ok=True)
    month_path = symbol_dir / "EURUSD_202510_ticks.parquet"
    _write_tick_parquet(
        month_path,
        [
            datetime(2025, 10, 3, 20, 59, 59, 574000, tzinfo=UTC),
        ],
    )
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.datetime",
        type(
            "FixedDateTime",
            (),
            {"now": staticmethod(lambda tz=None: datetime(2025, 10, 3, 21, 30, tzinfo=UTC))},
        ),
    )
    ranges = get_missing_months("EURUSD", out_dir, datetime(2025, 10, 3, 21, 30, tzinfo=UTC))
    assert ranges == []


def test_get_missing_months_appends_before_friday_close(monkeypatch, tmp_path: Path) -> None:
    out_dir = tmp_path / "dukascopy_ticks"
    symbol_dir = out_dir / "EURUSD"
    symbol_dir.mkdir(parents=True, exist_ok=True)
    month_path = symbol_dir / "EURUSD_202510_ticks.parquet"
    last_ts = datetime(2025, 10, 3, 19, 59, 59, tzinfo=UTC)
    _write_tick_parquet(month_path, [last_ts])
    monkeypatch.setattr(
        "scripts.download_tick_vault_data.datetime",
        type(
            "FixedDateTime",
            (),
            {"now": staticmethod(lambda tz=None: datetime(2025, 10, 3, 20, 30, tzinfo=UTC))},
        ),
    )
    ranges = get_missing_months("EURUSD", out_dir, datetime(2025, 10, 3, 20, 30, tzinfo=UTC))
    assert ranges == [(last_ts + timedelta(microseconds=1000), datetime(2025, 10, 3, 20, 30, tzinfo=UTC))]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_download_tick_vault_data.py -k "get_missing_months"`

Expected: the after-close test fails because the current code schedules a refill up to `end_date`.

- [ ] **Step 3: Add fetchable-end helpers and reorder current-month logic**

```python
def get_fetchable_end(now: datetime) -> datetime:
    now_utc = _normalize_utc(now)
    if is_fx_market_open(now_utc):
        return now_utc
    close_utc, reopen_utc = get_session_bounds_utc(now_utc)
    if now_utc < reopen_utc:
        return close_utc
    return now_utc


def get_missing_months(symbol: str, out_dir: Path, end_date: datetime) -> list[tuple[datetime, datetime]]:
    ranges_to_fill: list[tuple[datetime, datetime]] = []
    current = GLOBAL_START_DATE.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    now = datetime.now(tz=UTC)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    fetchable_end = get_fetchable_end(now)

    while current <= end_date:
        yyyymm = current.strftime("%Y%m")
        out_path = (out_dir / symbol) / f"{symbol}_{yyyymm}_ticks.parquet"
        month_end = min(current + relativedelta(months=1), end_date)

        if not out_path.exists():
            ranges_to_fill.append((current, month_end))
        elif current >= current_month_start:
            last_ts, _ = get_parquet_info(out_path)
            first_gap = find_first_market_gap(out_path)
            if first_gap:
                ranges_to_fill.append((first_gap, min(month_end, fetchable_end)))
            elif last_ts is not None:
                fill_start = last_ts + relativedelta(microseconds=1000)
                if fill_start < fetchable_end:
                    ranges_to_fill.append((fill_start, min(month_end, fetchable_end)))
        else:
            first_gap = find_first_market_gap(out_path)
            if first_gap:
                ranges_to_fill.append((first_gap, month_end))
            else:
                last_ts, _ = get_parquet_info(out_path)
                if last_ts is not None and is_fx_market_open(last_ts):
                    close_utc, _ = get_session_bounds_utc(last_ts)
                    if last_ts < close_utc:
                        ranges_to_fill.append((last_ts + relativedelta(microseconds=1000), month_end))

        current += relativedelta(months=1)

    return [(start, end) for start, end in ranges_to_fill if start < end]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -q tests/test_download_tick_vault_data.py -k "get_missing_months"`

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/download_tick_vault_data.py tests/test_download_tick_vault_data.py
git commit -m "fix: cap tick vault current-month refills at session end"
```

### Task 4: Add Conservative Stale-Lock Cleanup

**Files:**
- Modify: `scripts/download_tick_vault_data.py`
- Test: `tests/test_download_tick_vault_data.py`

- [ ] **Step 1: Write the failing stale-lock tests**

```python
from __future__ import annotations

from pathlib import Path

from scripts.download_tick_vault_data import should_clear_stale_lock


def test_should_clear_stale_lock_when_no_downloader_process(monkeypatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "download_tick_vault.lock"
    lock_path.touch()
    monkeypatch.setattr("scripts.download_tick_vault_data._list_process_commands", lambda: ["python app.py"])
    assert should_clear_stale_lock(lock_path) is True


def test_should_not_clear_lock_when_downloader_process_is_running(monkeypatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "download_tick_vault.lock"
    lock_path.touch()
    monkeypatch.setattr(
        "scripts.download_tick_vault_data._list_process_commands",
        lambda: ["python scripts/download_tick_vault_data.py --symbols EURUSD"],
    )
    assert should_clear_stale_lock(lock_path) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_download_tick_vault_data.py -k "stale_lock"`

Expected: `ImportError` or `AttributeError` for the new lock helper.

- [ ] **Step 3: Add process-list and stale-lock helpers, then use them in `main()`**

```python
import subprocess


def _list_process_commands() -> list[str]:
    result = subprocess.run(
        ["ps", "-ax", "-o", "command="],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def should_clear_stale_lock(lock_path: Path) -> bool:
    if not lock_path.exists():
        return False
    commands = _list_process_commands()
    return not any("scripts/download_tick_vault_data.py" in command for command in commands)


def _handle_existing_lock(lock_path: Path, force: bool) -> None:
    if not lock_path.exists() or force:
        return
    try:
        if should_clear_stale_lock(lock_path):
            logger.warning("Removing stale lockfile %s", lock_path)
            lock_path.unlink()
            return
    except Exception as exc:
        logger.warning("Could not verify stale lockfile %s: %s", lock_path, exc)
    logger.error("Lockfile %s exists. Another instance might be running. Use --force to override.", lock_path)
    sys.exit(1)
```

Then replace the existing lockfile branch in `main()` with:

```python
    lock_file = cache_dir / "download_tick_vault.lock"
    _handle_existing_lock(lock_file, args.force)
```

- [ ] **Step 4: Run the full targeted test file**

Run: `uv run pytest -q tests/test_download_tick_vault_data.py`

Expected: all downloader regression tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/download_tick_vault_data.py tests/test_download_tick_vault_data.py
git commit -m "fix: clear orphaned tick vault lockfiles"
```

### Task 5: Verify Against the Real Downloader Entry Point

**Files:**
- Modify: none
- Test: `tests/test_download_tick_vault_data.py`

- [ ] **Step 1: Run the dedicated downloader regression tests**

Run: `uv run pytest -q tests/test_download_tick_vault_data.py`

Expected: all tests pass.

- [ ] **Step 2: Run a bounded reproduction check for the Friday close case**

Run: `uv run python scripts/download_tick_vault_data.py --symbols EURUSD --force`

Expected log shape:

```text
[EURUSD] Data up to date. Skipping.
```

or, if the current month is genuinely behind before the close boundary:

```text
[EURUSD] Identified 1 ranges needing attention.
[EURUSD] [YYYYMM] Downloading range [...]
```

and not:

```text
Detected missing data hole starting at 2025-10-03 20:59:59...
Identified 99 ranges needing attention.
```

- [ ] **Step 3: Run the existing adjacent downloader test to catch regressions**

Run: `uv run pytest -q tests/test_download_histdata_ticks.py`

Expected: pass unchanged.

- [ ] **Step 4: Inspect the worktree**

Run: `git status --short`

Expected:

```text
 M scripts/download_tick_vault_data.py
 A tests/test_download_tick_vault_data.py
```

or a clean worktree if the task commits have already been created.

- [ ] **Step 5: Commit the final verification-safe state**

```bash
git add scripts/download_tick_vault_data.py tests/test_download_tick_vault_data.py
git commit -m "fix: stop tick vault weekend closure overfetching"
```

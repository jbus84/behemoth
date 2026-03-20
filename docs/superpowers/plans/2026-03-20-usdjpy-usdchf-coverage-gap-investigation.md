# USDJPY/USDCHF Coverage Gap Investigation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify why USDJPY (76.7%) and USDCHF (60%) show below-threshold signal coverage, confirm the warmup-gap root cause, and fix it properly by giving the JForex tester 1 day of startup data before the eval window begins.

**Architecture:** The JForex tester starts at `BEHEMOTH_JFOREX_START_UTC = 2025-07-07T00:00:00Z` (same as eval_start) with no prior warmup data. For 100-tick bars in the low-activity Tokyo / early-London session, the model doesn't accumulate enough warmup history to start predicting until 8–13 hours into the eval window. The proper fix is to move `DEFAULT_START` to `2025-07-06T00:00:00Z` (1 day before eval_start) so the model is fully warmed up by midnight July 7. This requires re-running the full 6-symbol matrix (~4–6 hours). After the re-run, `jforex-outcome-parity` is run with the unchanged `eval_start = 2025-07-07T00:00:00Z` and should show 100% coverage for all symbols.

**Tech Stack:** Python 3.11+, DuckDB, pandas, pytest, Makefile, Gradle/JForex

---

## Context

Pre-plan analysis (run 2026-03-20) produced these numbers for the `2025-07-07T00:00:00Z – 2025-07-09T00:00:00Z` eval window:

| Symbol  | locked | JFX sel | coverage | first_seen (UTC)     | warmup_gap |
|---------|--------|---------|----------|----------------------|------------|
| EURUSD  | 20     | 18      | 90.0%    | 2025-07-07 11:04 UTC | 3 preds    |
| GBPUSD  | 116    | 99      | 85.3%    | 2025-07-07 09:52 UTC | 6 preds    |
| USDJPY  | 103    | 79      | 76.7%    | 2025-07-07 08:29 UTC | 24 preds   |
| USDCHF  | 15     | 9       | 60.0%    | 2025-07-07 13:21 UTC | 7 preds    |
| AUDUSD  | 53     | 47      | 88.7%    | 2025-07-07 11:03 UTC | 5 preds    |
| USDCAD  | 50     | 50      | 100.0%   | 2025-07-07 13:00 UTC | 0 preds    |

`first_seen` = `MIN(close_ts)` in `audit_logs` (the Python API's per-selection log in `data/analysis/backtest_reconcile/runtime/{sym.lower()}_jforex_dukascopy_state.db`).
`warmup_gap` = locked predictions with `close_ts < first_seen` (never seen by JForex during warmup).

With `start_ts = 2025-07-06T00:00:00Z`, the model processes 1 full day of warmup before the eval window opens. All warmup gaps should become 0 and coverage should reach 100% for all symbols.

---

## File Map

- **Create:** `scripts/diagnose_jforex_coverage_gaps.py` — repeatable analysis: per-symbol warmup cutoff, gap count, and post-warmup coverage; used to verify the fix
- **Create:** `tests/test_diagnose_jforex_coverage_gaps.py` — unit tests for the diagnostic functions
- **Modify:** `scripts/run_jforex_dukascopy_matrix.py` — change `DEFAULT_START` from `2025-07-07T00:00:00Z` → `2025-07-06T00:00:00Z`
- **Modify:** `Makefile` — change `jforex-dukascopy-matrix` default `--start-ts` to match

---

### Task 1: Diagnostic script

**Files:**
- Create: `scripts/diagnose_jforex_coverage_gaps.py`
- Create: `tests/test_diagnose_jforex_coverage_gaps.py`

The script exposes three pure, testable functions used to verify before and after the fix:

```python
def load_audit_log_timestamps(db_path: Path, eval_end: str) -> list[datetime]:
    """Return all close_ts values from audit_logs with close_ts < eval_end (UTC)."""

def warmup_gap_count(locked_close_ts: list[datetime], warmup_cutoff: datetime) -> int:
    """Count locked predictions with close_ts < warmup_cutoff."""

def post_warmup_coverage(
    jforex_selected_total: int,
    locked_after_cutoff: int,
) -> float:
    """signal_coverage_ratio after excluding warmup-gap predictions from denominator."""
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_diagnose_jforex_coverage_gaps.py`:

```python
"""Tests for JForex coverage gap diagnostic functions."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from scripts.diagnose_jforex_coverage_gaps import (
    load_audit_log_timestamps,
    post_warmup_coverage,
    warmup_gap_count,
)


def _make_audit_db(tmp_path: Path, close_timestamps_utc: list[str]) -> Path:
    """Create a minimal audit_logs DuckDB at tmp_path/state.db."""
    db_path = tmp_path / "state.db"
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE audit_logs ("
        "  event_ts TIMESTAMPTZ,"
        "  close_ts TIMESTAMPTZ,"
        "  symbol VARCHAR,"
        "  candidate_uid VARCHAR,"
        "  pred_prob DOUBLE,"
        "  threshold DOUBLE,"
        "  features_json VARCHAR,"
        "  model_month VARCHAR,"
        "  run_id VARCHAR"
        ")"
    )
    for ts in close_timestamps_utc:
        con.execute(
            "INSERT INTO audit_logs(event_ts, close_ts) VALUES (NOW(), ?::TIMESTAMPTZ)",
            [ts],
        )
    con.close()
    return db_path


def test_load_audit_log_timestamps_returns_utc_datetimes(tmp_path: Path) -> None:
    db = _make_audit_db(
        tmp_path,
        ["2025-07-07T08:30:00Z", "2025-07-07T10:00:00Z", "2025-07-08T12:00:00Z"],
    )
    result = load_audit_log_timestamps(db, eval_end="2025-07-09T00:00:00Z")
    assert len(result) == 3
    assert all(ts.tzinfo is not None for ts in result)
    assert min(result) == datetime(2025, 7, 7, 8, 30, tzinfo=timezone.utc)


def test_load_audit_log_timestamps_excludes_entries_after_eval_end(tmp_path: Path) -> None:
    db = _make_audit_db(
        tmp_path,
        ["2025-07-07T08:30:00Z", "2025-07-09T01:00:00Z"],  # second is past eval_end
    )
    result = load_audit_log_timestamps(db, eval_end="2025-07-09T00:00:00Z")
    assert len(result) == 1


def test_load_audit_log_timestamps_empty_db(tmp_path: Path) -> None:
    db = _make_audit_db(tmp_path, [])
    result = load_audit_log_timestamps(db, eval_end="2025-07-09T00:00:00Z")
    assert result == []


def test_warmup_gap_count_counts_predictions_before_cutoff() -> None:
    locked = [
        datetime(2025, 7, 7, 0, 0, tzinfo=timezone.utc),
        datetime(2025, 7, 7, 5, 0, tzinfo=timezone.utc),
        datetime(2025, 7, 7, 9, 0, tzinfo=timezone.utc),
    ]
    cutoff = datetime(2025, 7, 7, 8, 30, tzinfo=timezone.utc)
    assert warmup_gap_count(locked, cutoff) == 2


def test_warmup_gap_count_zero_when_all_after_cutoff() -> None:
    locked = [datetime(2025, 7, 7, 10, 0, tzinfo=timezone.utc)]
    cutoff = datetime(2025, 7, 7, 8, 30, tzinfo=timezone.utc)
    assert warmup_gap_count(locked, cutoff) == 0


def test_post_warmup_coverage_exact_match() -> None:
    assert post_warmup_coverage(jforex_selected_total=79, locked_after_cutoff=79) == pytest.approx(1.0)


def test_post_warmup_coverage_ratio_above_one_is_valid() -> None:
    # jforex_selected includes warmup-period selections; ratio > 1.0 is valid (not clamped)
    ratio = post_warmup_coverage(jforex_selected_total=79, locked_after_cutoff=69)
    assert ratio > 1.0  # 1.14 — reported as-is


def test_post_warmup_coverage_zero_locked_returns_zero() -> None:
    assert post_warmup_coverage(jforex_selected_total=5, locked_after_cutoff=0) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/danielfisher/repositories/behemoth
uv run pytest tests/test_diagnose_jforex_coverage_gaps.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'load_audit_log_timestamps'`

- [ ] **Step 3: Implement `scripts/diagnose_jforex_coverage_gaps.py`**

```python
#!/usr/bin/env python3
"""Diagnose JForex tester warmup-gap coverage issues per symbol.

For each symbol, compares the audit_logs first-seen timestamp against locked
predictions to quantify how many predictions fall in the warmup window and
what coverage would be under a range of candidate eval_start values.

Run before and after the start_ts fix to verify warmup_gap drops to 0.

Usage:
    uv run python scripts/diagnose_jforex_coverage_gaps.py

Output: console table — no files written.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb


DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
DEFAULT_LOCK_DIR = Path("configs/research/governance/oco_history_dukascopy_candidate/2025-07")
DEFAULT_STATE_DB_DIR = Path("data/analysis/backtest_reconcile/runtime")
DEFAULT_EVAL_START = "2025-07-07T00:00:00Z"
DEFAULT_EVAL_END = "2025-07-09T00:00:00Z"
CANDIDATE_EVAL_STARTS = [
    "2025-07-07T00:00:00Z",
    "2025-07-07T08:00:00Z",
    "2025-07-07T10:00:00Z",
    "2025-07-07T12:00:00Z",
    "2025-07-07T14:00:00Z",
]


def load_audit_log_timestamps(db_path: Path, eval_end: str) -> list[datetime]:
    """Return all audit_log close_ts values with close_ts < eval_end, as UTC datetimes."""
    if not db_path.exists():
        return []
    con = duckdb.connect(str(db_path), read_only=True)
    rows = con.execute(
        "SELECT close_ts AT TIME ZONE 'UTC' FROM audit_logs "
        "WHERE close_ts::TIMESTAMPTZ < ?::TIMESTAMPTZ",
        [eval_end],
    ).fetchall()
    con.close()
    return [
        r[0].replace(tzinfo=timezone.utc) if r[0].tzinfo is None else r[0].astimezone(timezone.utc)
        for r in rows
    ]


def warmup_gap_count(locked_close_ts: list[datetime], warmup_cutoff: datetime) -> int:
    """Count locked predictions with close_ts strictly before warmup_cutoff."""
    return sum(1 for ts in locked_close_ts if ts < warmup_cutoff)


def post_warmup_coverage(jforex_selected_total: int, locked_after_cutoff: int) -> float:
    """signal_coverage_ratio = jforex_selected_total / locked_after_cutoff.

    May exceed 1.0 when jforex_selected_total includes warmup-period selections
    that are excluded from locked_after_cutoff (not a bug — just reported as-is).
    """
    if locked_after_cutoff == 0:
        return 0.0
    return jforex_selected_total / locked_after_cutoff


def _load_locked_close_ts(lock_dir: Path, symbol: str, eval_start: str, eval_end: str) -> list[datetime]:
    path = lock_dir / f"{symbol.lower()}_oco_locked_predictions.parquet"
    con = duckdb.connect()
    rows = con.execute(
        "SELECT close_ts AT TIME ZONE 'UTC' FROM read_parquet(?) "
        "WHERE selected_exec = 1 "
        "AND close_ts::TIMESTAMPTZ >= ?::TIMESTAMPTZ "
        "AND close_ts::TIMESTAMPTZ < ?::TIMESTAMPTZ",
        [str(path), eval_start, eval_end],
    ).fetchall()
    con.close()
    return [
        r[0].replace(tzinfo=timezone.utc) if r[0].tzinfo is None else r[0].astimezone(timezone.utc)
        for r in rows
    ]


def main() -> None:
    print(f"\n{'Symbol':<8} {'first_seen_utc':<22} {'gap':>5}", end="")
    for es in CANDIDATE_EVAL_STARTS:
        label = es[11:16]  # e.g. "14:00"
        print(f"  cov@{label}", end="")
    print()
    print("-" * (8 + 22 + 5 + len(CANDIDATE_EVAL_STARTS) * 11))

    for symbol in DEFAULT_SYMBOLS:
        db_path = DEFAULT_STATE_DB_DIR / f"{symbol.lower()}_jforex_dukascopy_state.db"
        audit_ts = load_audit_log_timestamps(db_path, DEFAULT_EVAL_END)
        first_seen = min(audit_ts) if audit_ts else None
        # len(audit_ts) matches jforex_selected_total from the runtime CSV because each
        # audit_log row corresponds to exactly one selected_exec=1 API call. Verified
        # against the runtime CSV counts for all 6 symbols in the 2026-03-20 run.
        jforex_selected = len(audit_ts)

        locked_full = _load_locked_close_ts(DEFAULT_LOCK_DIR, symbol, DEFAULT_EVAL_START, DEFAULT_EVAL_END)
        gap = warmup_gap_count(locked_full, first_seen) if first_seen else len(locked_full)

        first_seen_str = first_seen.strftime("%Y-%m-%d %H:%M") if first_seen else "N/A"
        print(f"{symbol:<8} {first_seen_str:<22} {gap:>5}", end="")

        for es in CANDIDATE_EVAL_STARTS:
            locked_after = _load_locked_close_ts(DEFAULT_LOCK_DIR, symbol, es, DEFAULT_EVAL_END)
            ratio = post_warmup_coverage(jforex_selected, len(locked_after))
            print(f"  {ratio:>9.1%}", end="")
        print()

    print(f"\nNote: cov@HH:MM = jforex_selected / locked_count with eval_start=HH:MM UTC on 2025-07-07")
    print("      ratio > 1.0 is expected when jforex_selected includes warmup-period selections")
    print("      After the start_ts fix: gap=0 and cov@00:00=100% for all symbols")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_diagnose_jforex_coverage_gaps.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Run the diagnostic on the current (broken) run to establish the baseline**

```bash
uv run python scripts/diagnose_jforex_coverage_gaps.py
```

Expected output (header `cov@HH:MM` = 11 chars; data `  {ratio:>9.1%}` = 11 chars):
```
Symbol   first_seen_utc           gap  cov@00:00  cov@08:00  cov@10:00  cov@12:00  cov@14:00
-----------------------------------------------------------------------------------------------
EURUSD   2025-07-07 11:04           3      90.0%      ...        ...        ...       120.0%
GBPUSD   2025-07-07 09:52           6      85.3%      ...        ...        ...       104.2%
USDJPY   2025-07-07 08:29          24      76.7%      ...        ...        ...       114.5%
USDCHF   2025-07-07 13:21           7      60.0%      ...        ...        ...       128.6%
AUDUSD   2025-07-07 11:03           5      88.7%      ...        ...        ...       102.2%
USDCAD   2025-07-07 13:00           0     100.0%      ...        ...        ...       122.0%
```

This confirms the baseline before the fix. Save this output for comparison.

- [ ] **Step 6: Run full test suite to check no regressions**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/diagnose_jforex_coverage_gaps.py tests/test_diagnose_jforex_coverage_gaps.py
git commit -m "feat: add JForex coverage-gap diagnostic script

Identifies warmup-gap predictions (those before JForex first-seen timestamp)
per symbol and shows expected signal_coverage_ratio under candidate eval_start
values. Baseline confirms USDJPY gap=24, USDCHF gap=7 — fixed by moving
start_ts to 2025-07-06 to give the model 1 day of warmup before eval window.

The broken run started at 2025-07-07 (eval_start) with zero warmup data. USDCHFu2019s
warmup cutoff was 13:21 UTC July 7 starting from midnight with no history — 1 day
of prior ticks (midnight July 6) comfortably covers the ~290 bars needed and halves
the Dukascopy download vs. the 2-day approach."
```

---

### Task 2: Move DEFAULT_START 1 day earlier

**Files:**
- Modify: `scripts/run_jforex_dukascopy_matrix.py` — one-line change to `DEFAULT_START`
- Modify: `Makefile` — one-line change to `jforex-dukascopy-matrix` default `--start-ts`

Both need updating: the Python constant is the default when running the script directly; the Makefile hardcodes its own default and passes `--start-ts` explicitly, overriding the Python constant.

- [ ] **Step 1: Update `DEFAULT_START` in `scripts/run_jforex_dukascopy_matrix.py`**

Find:
```python
DEFAULT_START = "2025-07-07T00:00:00Z"
```

Change to:
```python
DEFAULT_START = "2025-07-06T00:00:00Z"
```

- [ ] **Step 2: Update the Makefile `jforex-dukascopy-matrix` default `--start-ts`**

In the `jforex-dukascopy-matrix` target, find:
```makefile
--start-ts $(or $(START_TS),2025-07-07T00:00:00Z) \
```

Change to:
```makefile
--start-ts $(or $(START_TS),2025-07-06T00:00:00Z) \
```

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all pass (the change is data-only, no logic change).

- [ ] **Step 4: Commit**

```bash
git add scripts/run_jforex_dukascopy_matrix.py Makefile
git commit -m "fix: move jforex-dukascopy-matrix start_ts to 2025-07-06 for proper warmup

The JForex tester was starting at eval_start (2025-07-07) with no prior
warmup data. For 100-tick bars in the Tokyo session, the model needed 8-13h
to accumulate enough history before it could predict — causing USDJPY (gap=24)
and USDCHF (gap=7) to miss predictions at the start of the eval window.
Two days of warmup data eliminates the gap for all symbols."
```

---

### Task 3: Re-run the full 6-symbol matrix

**Note:** This task takes ~4–6 hours (real Dukascopy tick data downloads). Start it and wait for completion.

- [ ] **Step 1: Verify no stale processes are running on port 8000**

```bash
lsof -ti:8000
```

If any PIDs are listed, kill them: `lsof -ti:8000 | xargs kill -9`

- [ ] **Step 2: Run the matrix**

```bash
cd /Users/danielfisher/repositories/behemoth
make jforex-dukascopy-matrix 2>&1 | tee logs/jforex_dukascopy_matrix_$(date +%Y%m%d_%H%M%S).log
```

Expected log output per symbol:
```
[jforex-dukascopy] EURUSD: starting API
[jforex-dukascopy] EURUSD: running JForex tester
[jforex-dukascopy] EURUSD: complete
...
[jforex-dukascopy] USDCAD: complete
```

If a symbol fails, check the per-symbol API log at `logs/api_{symbol.lower()}.log`.

- [ ] **Step 3: Verify all 6 CSV files were written**

```bash
ls -la data/analysis/backtest_reconcile/*_jforex_runtime_events.csv
```

Expected: 6 files, all updated within the last hour, all non-empty.

---

### Task 4: Verify the fix with the diagnostic

- [ ] **Step 1: Run the diagnostic on the new run**

```bash
uv run python scripts/diagnose_jforex_coverage_gaps.py
```

Expected: all symbols show `gap=0` and `cov@00:00 ≈ 100%`:
```
Symbol   first_seen_utc           gap  cov@00:00  ...
------------------------------------------------------
EURUSD   2025-07-07 00:XX           0     100.0%  ...
GBPUSD   2025-07-07 00:XX           0     100.0%  ...
USDJPY   2025-07-07 00:XX           0     100.0%  ...
USDCHF   2025-07-07 00:XX           0     100.0%  ...
AUDUSD   2025-07-07 00:XX           0     100.0%  ...
USDCAD   2025-07-07 00:XX           0     100.0%  ...
```

If any symbol still shows `gap > 0`, investigate: the warmup may still be insufficient for that symbol. Consider moving `DEFAULT_START` to `2025-07-04T00:00:00Z` and re-running that symbol alone.

- [ ] **Step 2: Run `make jforex-outcome-parity` to confirm all symbols pass**

`$(SYMBOLS)` defaults to all 6 symbols via `SYMBOLS ?= EURUSD,...` at the top of the Makefile — no override needed.

```bash
make jforex-outcome-parity 2>&1
```

Expected (eval_start=`2025-07-07T00:00:00Z`, threshold=1.0):
```
Symbol    Locked  JFX Sel  Coverage   Orders   ExecOK  Verdict
--------------------------------------------------------------
EURUSD        20       20    100.0%        X      yes     PASS
GBPUSD       116      116    100.0%        X      yes     PASS
USDJPY       103      103    100.0%        X      yes     PASS
USDCHF        15       15    100.0%        X      yes     PASS
AUDUSD        53       53    100.0%        X      yes     PASS
USDCAD        50       50    100.0%        X      yes     PASS
```

---

### Task 5: Run full Stage 14 certification

- [ ] **Step 1: Run `make full-stage14-cert`**

```bash
make full-stage14-cert 2>&1
```

Expected: all 7 Stage 14 checks pass; snapshot written to `docs/strategy_bible/generated/stage_14_snapshot.md`.

If `local-jforex-cert` or `stage14-jforex-cert` fails on a check other than outcome parity, investigate separately — those would be pre-existing issues unrelated to the warmup fix.

- [ ] **Step 2: Commit certification artifacts**

```bash
git add data/analysis/backtest_reconcile/
git add docs/strategy_bible/generated/stage_14_snapshot.md
git add docs/analysis/
git commit -m "chore: stage14 certification artifacts — all-green snapshot 2026-03-20

Re-run with start_ts=2025-07-06 eliminates warmup gap for all 6 symbols.
All stage14 checks pass including jforex_outcome_parity (100% coverage)."
```

---

## Verification

After all tasks complete:

```bash
# Confirm outcome parity all PASS
grep "overall_pass" data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv

# Confirm per-symbol files updated for previously-failing symbols
grep "jforex_outcome_parity_pass" data/analysis/backtest_reconcile/USDJPY_local_jforex_outcome_parity_summary.csv
grep "jforex_outcome_parity_pass" data/analysis/backtest_reconcile/USDCHF_local_jforex_outcome_parity_summary.csv
```

---

## Alternative: eval_start adjustment (not recommended)

If re-running the matrix is not currently feasible, the eval window can be narrowed to exclude the warmup gap using existing run data. Change the Makefile `jforex-outcome-parity` default `--eval-start` from `2025-07-07T00:00:00Z` to `2025-07-07T14:00:00Z`. With this change, `locked_count` shrinks (warmup-gap predictions are excluded from the denominator) while `jforex_selected_total` stays the same, making all six symbols achieve `signal_coverage_ratio ≥ 1.0`.

This is a measurement adjustment, not a fix — it papers over the root cause and reduces the sample window by 14 hours. Every future matrix run that starts at eval_start will have the same warmup gap until `DEFAULT_START` is moved. Use this only as a temporary workaround.

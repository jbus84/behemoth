# Spotlight Coverage Fix Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `order_coverage_ratio` from ~2–7% to ~100% by sourcing spotlight tick extraction from locked predictions (single candidate) instead of monthly predictions (all candidates).

**Architecture:** The cursor contamination root cause: `extract_spotlight_ticks.py` reads ALL monthly selected events across all candidates, producing ~373 wrong-candidate bar closes for EURUSD that advance the locked candidate's `candidate_cursor` before its 20 real events arrive. Fix: add `--lock-dir` parameter to source extraction from `{lock_dir}/{symbol}_oco_locked_predictions.parquet` (same schema, single candidate, already `selected_exec=1` filtered). Also set `--pre-bars 0` to eliminate warmup-bar cursor contamination entirely.

**Tech Stack:** Python, argparse, duckdb, pytest, GNU Make

---

## Root Cause Reference

- Monthly predictions parquet: 417 EURUSD `selected_exec=1` events in eval window (all candidates)
- Locked predictions parquet: 20 EURUSD events (1 candidate: `oco_first_touch_clean__high_abs_vel_q80__k2`)
- Spotlight extracts 904 total bar closes → 373 are non-locked-candidate events
- API server `tolerant` mode: monotonically advancing `candidate_cursor` advances through locked candidate's 123-entry prediction index when wrong-candidate bar closes fall within 120s of any non-selected locked entry → cursor exhausted before real events arrive
- Fix: extract ticks for locked events only → 0 wrong-candidate bar closes → 100% cursor hits

## File Map

| File | Change |
|------|--------|
| `scripts/extract_spotlight_ticks.py` | Add `--lock-dir` parameter; use locked parquet path when provided |
| `Makefile` | Pass `--lock-dir` + `--pre-bars 0` to spotlight extraction; raise threshold to 0.8 |
| `tests/test_extract_spotlight_ticks.py` | New: unit tests for locked-source extraction path |

---

### Task 1: Add `--lock-dir` to `extract_spotlight_ticks.py`

**Files:**
- Modify: `scripts/extract_spotlight_ticks.py`
- Test: `tests/test_extract_spotlight_ticks.py`

**Context:**

The locked predictions parquet schema (same as monthly):
- `test_month` (str, e.g. `"2025-07"`)
- `close_ts` (TIMESTAMPTZ, BST +01:00)
- `selected_exec` (int, 0/1)
- `candidate_uid`, `pred_prob`, etc.

Path convention: `{lock_dir}/{symbol.lower()}_oco_locked_predictions.parquet`
e.g. `configs/research/governance/oco_history_dukascopy_candidate/2025-07/eurusd_oco_locked_predictions.parquet`

The existing `_extract_symbol(symbol, pred_path, ...)` takes `pred_path` as a `Path` — no changes to `_extract_symbol` needed, only to how `pred_path` is resolved in `main()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_extract_spotlight_ticks.py`:

```python
"""Tests for extract_spotlight_ticks --lock-dir path resolution."""
from __future__ import annotations

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def _import_main():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "extract_spotlight_ticks",
        Path(__file__).parents[1] / "scripts" / "extract_spotlight_ticks.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_lock_dir_resolves_locked_parquet(tmp_path):
    """When --lock-dir is given, pred_path uses locked parquet, not monthly."""
    mod = _import_main()

    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    locked_parquet = lock_dir / "eurusd_oco_locked_predictions.parquet"
    locked_parquet.touch()

    calls = []

    def fake_extract_symbol(symbol, pred_path, **kwargs):
        calls.append((symbol, pred_path))

    tick_root = tmp_path / "ticks"
    (tick_root / "EURUSD").mkdir(parents=True)
    (tick_root / "EURUSD" / "ticks.parquet").touch()

    with patch.object(mod, "_extract_symbol", side_effect=fake_extract_symbol):
        with patch.object(
            sys,
            "argv",
            [
                "extract_spotlight_ticks.py",
                "--symbols", "EURUSD",
                "--lock-dir", str(lock_dir),
                "--tick-root", str(tick_root),
                "--output-dir", str(tmp_path / "out"),
                "--model-month", "2025-07",
                "--eval-start", "",
                "--eval-end", "",
            ],
        ):
            mod.main()

    assert len(calls) == 1
    symbol, pred_path = calls[0]
    assert symbol == "EURUSD"
    assert pred_path == locked_parquet


def test_no_lock_dir_falls_back_to_monthly(tmp_path):
    """When --lock-dir is absent, pred_path uses monthly predictions parquet."""
    mod = _import_main()

    predictions_dir = tmp_path / "preds"
    predictions_dir.mkdir()
    monthly_parquet = predictions_dir / "EURUSD_oco_monthly_predictions.parquet"
    monthly_parquet.touch()

    calls = []

    def fake_extract_symbol(symbol, pred_path, **kwargs):
        calls.append((symbol, pred_path))

    tick_root = tmp_path / "ticks"
    (tick_root / "EURUSD").mkdir(parents=True)
    (tick_root / "EURUSD" / "ticks.parquet").touch()

    with patch.object(mod, "_extract_symbol", side_effect=fake_extract_symbol):
        with patch.object(
            sys,
            "argv",
            [
                "extract_spotlight_ticks.py",
                "--symbols", "EURUSD",
                "--predictions-dir", str(predictions_dir),
                "--tick-root", str(tick_root),
                "--output-dir", str(tmp_path / "out"),
                "--model-month", "2025-07",
                "--eval-start", "",
                "--eval-end", "",
            ],
        ):
            mod.main()

    assert len(calls) == 1
    symbol, pred_path = calls[0]
    assert symbol == "EURUSD"
    assert pred_path == monthly_parquet


def test_lock_dir_missing_parquet_is_skipped(tmp_path, capsys):
    """Missing locked parquet for a symbol prints a warning and skips (no crash)."""
    mod = _import_main()

    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    # Do NOT create the locked parquet

    tick_root = tmp_path / "ticks"
    (tick_root / "EURUSD").mkdir(parents=True)
    (tick_root / "EURUSD" / "ticks.parquet").touch()

    with patch.object(sys, "argv", [
        "extract_spotlight_ticks.py",
        "--symbols", "EURUSD",
        "--lock-dir", str(lock_dir),
        "--tick-root", str(tick_root),
        "--output-dir", str(tmp_path / "out"),
        "--model-month", "2025-07",
        "--eval-start", "",
        "--eval-end", "",
    ]):
        with pytest.raises(SystemExit):
            mod.main()

    captured = capsys.readouterr()
    assert "not found" in captured.err.lower() or "eurusd" in captured.err.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_extract_spotlight_ticks.py -v
```

Expected: FAIL — `--lock-dir` arg doesn't exist yet.

- [ ] **Step 3: Add `--lock-dir` to `extract_spotlight_ticks.py`**

Update the `DEFAULT_PRE_BARS` constant at line 29 so direct script invocations match the Makefile default:

```python
DEFAULT_PRE_BARS = 0
```

In `_parse_args()`, after the `--max-events` argument:

```python
parser.add_argument(
    "--lock-dir",
    default="",
    help="Directory containing locked prediction parquets "
    "({lock_dir}/{symbol.lower()}_oco_locked_predictions.parquet). "
    "When set, uses locked predictions as the event source instead of "
    "monthly predictions — eliminates wrong-candidate cursor contamination.",
)
```

In `main()`, replace the `pred_path` resolution block:

```python
# Before (monthly predictions):
pred_path = predictions_dir / f"{symbol}_oco_monthly_predictions.parquet"
if not pred_path.exists():
    print(f"[spotlight] {symbol}: predictions file not found: {pred_path}", file=sys.stderr)
    failures.append(symbol)
    continue
```

With:

```python
# Resolve event source: locked predictions (preferred) or monthly predictions
lock_dir = Path(args.lock_dir) if args.lock_dir.strip() else None
if lock_dir is not None:
    pred_path = lock_dir / f"{symbol.lower()}_oco_locked_predictions.parquet"
else:
    pred_path = predictions_dir / f"{symbol}_oco_monthly_predictions.parquet"

if not pred_path.exists():
    print(f"[spotlight] {symbol}: predictions file not found: {pred_path}", file=sys.stderr)
    failures.append(symbol)
    continue
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_extract_spotlight_ticks.py -v
```

Expected: 3/3 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_spotlight_ticks.py tests/test_extract_spotlight_ticks.py
git commit -m "feat: add --lock-dir to extract_spotlight_ticks to eliminate cursor contamination"
```

---

### Task 2: Update Makefile spotlight target

**Files:**
- Modify: `Makefile` (lines 107–146, `local-jforex-parity-spotlight` target)

**Context:**

Current extraction invocation in spotlight target:
```makefile
UV_CACHE_DIR=... uv run python scripts/extract_spotlight_ticks.py \
    --symbols ... \
    --model-month ... \
    --predictions-dir ... \       ← uses monthly predictions
    --tick-root ... \
    --output-dir ... \
    --eval-start ... \
    --eval-end ... \
    --pre-bars $(or $(PRE_BARS),3) \    ← 3 warmup bars = 300 extra ticks per event
    --max-events ...
```

Changes needed:
1. Add `--lock-dir` pointing to the governance lock directory for the model month
2. Change `--pre-bars` default to `0` (no warmup bars → no wrong-candidate closes before event bar)
3. Raise `--signal-coverage-threshold` from 0.01 back to 0.8
4. Remove the "NOTE: threshold=0.01 above is interim" comment block

- [ ] **Step 1: Update the Makefile extraction step and reconcile threshold**

Replace the extraction block (lines ~107–116) from:
```makefile
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/extract_spotlight_ticks.py \
		--symbols $(or $(SYMBOLS),EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD) \
		--model-month $(or $(MODEL_MONTH),2025-07) \
		--predictions-dir $(or $(PREDICTIONS_DIR),data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2025_m3to1_oco_fullcap) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks) \
		--output-dir $(or $(SPOTLIGHT_DIR),data/analysis/spotlight_ticks) \
		--eval-start $(or $(EVAL_START),2025-07-07T00:00:00Z) \
		--eval-end $(or $(EVAL_END),2025-07-09T00:00:00Z) \
		--pre-bars $(or $(PRE_BARS),3) \
		--max-events $(or $(MAX_EVENTS),600)
```

To:
```makefile
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/extract_spotlight_ticks.py \
		--symbols $(or $(SYMBOLS),EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD) \
		--model-month $(or $(MODEL_MONTH),2025-07) \
		--lock-dir $(or $(LOCK_DIR),configs/research/governance/oco_history_dukascopy_candidate/$(or $(MODEL_MONTH),2025-07)) \
		--tick-root $(or $(TICK_ROOT),/Users/danielfisher/Desktop/dukascopy_ticks) \
		--output-dir $(or $(SPOTLIGHT_DIR),data/analysis/spotlight_ticks) \
		--eval-start $(or $(EVAL_START),2025-07-07T00:00:00Z) \
		--eval-end $(or $(EVAL_END),2025-07-09T00:00:00Z) \
		--pre-bars $(or $(PRE_BARS),0)
```

Note: `--predictions-dir` is dropped (unused when `--lock-dir` is set). `--max-events` is dropped (locked parquet per symbol has only the events for that locked candidate — no need to cap).

Replace the reconcile threshold line (line ~143):
```makefile
		--signal-coverage-threshold $(or $(SIGNAL_COVERAGE_THRESHOLD),0.01) \
```
With:
```makefile
		--signal-coverage-threshold $(or $(SIGNAL_COVERAGE_THRESHOLD),0.8) \
```

Remove the interim comment block (lines ~145–146):
```makefile
# NOTE: threshold=0.01 above is interim — spotlight bar alignment produces ~2-7% coverage.
# See docs/superpowers/plans/2026-03-18-stage14-full-outcome-reconciliation.md Task 7
# for the investigation guide. Raise to 0.8 once bar alignment is fixed.
```

- [ ] **Step 2: Verify Makefile parses cleanly**

```bash
make help 2>&1 | grep spotlight
```

Expected: `local-jforex-parity-spotlight` appears in help output with no errors.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "fix: spotlight target uses locked predictions and pre-bars=0 to fix cursor contamination"
```

---

### Task 3: Run spotlight pipeline and verify coverage

**Context:**

This is a live pipeline run against real tick data and the governance lock. Prerequisites:
- Tick data at `/Users/danielfisher/Desktop/dukascopy_ticks/{SYMBOL}/*.parquet`
- Python API server dependencies installed (`uv sync`)
- Java/Gradle (via `mise`) available

Expected after fix:
- Each symbol: `n_events` matches locked predictions count for eval window; `n_matched` == `n_events`
- `order_coverage_ratio` ≈ 1.0 per symbol (locked events get bar closes that hit cursor exactly)
- `jforex_outcome_parity_pass = True` per symbol
- `overall_pass = True` in `jforex_outcome_parity_summary.csv`

- [ ] **Step 1: Run extraction only (fast check, no Java)**

```bash
uv run python scripts/extract_spotlight_ticks.py \
    --symbols EURUSD \
    --model-month 2025-07 \
    --lock-dir configs/research/governance/oco_history_dukascopy_candidate/2025-07 \
    --tick-root /Users/danielfisher/Desktop/dukascopy_ticks \
    --output-dir /tmp/spotlight_test \
    --eval-start 2025-07-07T00:00:00Z \
    --eval-end 2025-07-09T00:00:00Z \
    --pre-bars 0
```

Expected output:
```
[spotlight] EURUSD: N events, N matched, ~2000 ticks  [... .. ...]
```

Where N ≈ 20 (locked events for EURUSD in eval window). Confirm tick count ≈ N × 100 or less (DISTINCT deduplication merges ticks shared between adjacent event windows).

- [ ] **Step 2: Run full spotlight pipeline**

```bash
make local-jforex-parity-spotlight
```

Expected terminal output per symbol: `[local-jforex] EURUSD: complete` etc., then reconcile output showing `order_coverage_ratio ≥ 0.8` for each symbol.

- [ ] **Step 3: Check reconcile output**

```bash
uv run python -c "
import pandas as pd
df = pd.read_csv('data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv')
print(df[['symbol','locked_count','order_coverage_ratio','order_coverage_pass','overall_pass']].to_string())
"
```

Expected: `order_coverage_pass = True` and `overall_pass = True` for all 6 symbols.

- [ ] **Step 4: Run cert**

```bash
make local-jforex-cert
```

Expected: `JFOREX_OUTCOME_PARITY_PASS status=pass` in the summary checks CSV.

- [ ] **Step 5: Commit**

Only if the pipeline run produces clean results. No code changes in this task — commit the updated summary CSVs if appropriate, or just verify and leave data files uncommitted.

---

## Verification Summary

Pass criteria (same as Stage 14 cert):
- `order_coverage_ratio ≥ 0.8` per symbol
- `jforex_outcome_parity_pass = True` per symbol
- `JFOREX_OUTCOME_PARITY_PASS status=pass` in cert output

Fallback: if any symbol shows 0 matched events, check that `--eval-start`/`--eval-end` UTC window aligns with locked parquet `close_ts` values (stored as BST +01:00, server normalizes to UTC). Run:
```bash
uv run python -c "
import duckdb
con = duckdb.connect()
df = con.execute(\"\"\"
SELECT COUNT(*), MIN(close_ts::TIMESTAMPTZ), MAX(close_ts::TIMESTAMPTZ)
FROM read_parquet('configs/research/governance/oco_history_dukascopy_candidate/2025-07/eurusd_oco_locked_predictions.parquet')
WHERE selected_exec = 1
  AND close_ts::TIMESTAMPTZ >= '2025-07-07T00:00:00Z'::TIMESTAMPTZ
  AND close_ts::TIMESTAMPTZ < '2025-07-09T00:00:00Z'::TIMESTAMPTZ
\"\"\").fetchdf()
print(df)
"
```

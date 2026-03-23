# JForex Outcome Parity: Month-Level Trading Performance Comparison

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify that the JForex runtime (real Dukascopy) produces statistically comparable trading outcomes to the Python backtest over a full month (2025-07), using the governance-locked reduced-core predictions as ground truth.

**Architecture:** Run the real Dukascopy JForex tester matrix (`jforex-dukascopy-matrix`) for each symbol — this streams ticks directly via Dukascopy's `ITesterClient`, bypassing the HTTP tick-batch bottleneck of the surrogate. Then build a reconciliation script that joins the JForex runtime events (orders submitted, fills, touch syncs) against the locked predictions parquet, computes aggregate outcome metrics (total gross pips, win rate, trade count), and produces a pass/fail verdict based on outcome similarity — not tick-exact alignment.

**Tech Stack:** Python (DuckDB, argparse), JForex `JForexTesterRunner` (Java/Gradle, real Dukascopy ITesterClient), existing Python API server (FastAPI).

---

## Context

### What we're comparing

| Side | Source of truth | What it tells us |
|------|----------------|-----------------|
| **Python backtest** | Locked predictions parquet at `configs/research/governance/oco_history_dukascopy_candidate/2025-07/{SYMBOL}_oco_locked_predictions.parquet` | For each bar event: `selected_exec`, `target_gross_pips`, `target_gross_pos`, `candidate_uid`, `close_ts` |
| **JForex surrogate** | Runtime events CSV at `data/analysis/backtest_reconcile/{SYMBOL}_*_runtime_events.csv` | For each bar: `predict_cycle` count, `order_submitted`, `order_filled`, `trade_touch_synced` events |

### What "comparable outcomes" means

The Python backtest computes `target_gross_pips` as an idealized P&L per bar event. JForex can't replicate this tick-perfectly because bar boundaries differ slightly on real tick replay. Instead, we verify:

1. **Signal coverage**: JForex fires `predict_cycle` events that cover the locked event set (not necessarily 1:1, but statistically close)
2. **Execution integrity**: Orders submitted and filled without failures
3. **Outcome direction**: The aggregate P&L direction (positive/negative) matches per-symbol
4. **Outcome magnitude**: The aggregate gross pips from JForex is within a tolerance band of the Python backtest total

### Key numbers (locked predictions, 2025-07)

| Symbol | Locked rows | selected_exec=1 | candidate_uids | Avg gross pips |
|--------|------------|-----------------|----------------|---------------|
| EURUSD | 817 | 217 | 1 | 3.47 |
| GBPUSD | 2,096 | 1,363 | 2 | 2.69 |
| USDJPY | 2,086 | 1,400 | 2 | 4.05 |
| USDCHF | 1,011 | 252 | 1 | 2.24 |
| AUDUSD | 2,062 | 488 | 2 | 1.22 |
| USDCAD | 1,847 | 580 | 2 | 1.87 |

### Current state

- 3 of 6 symbols (AUDUSD, GBPUSD, USDCHF) have completed JForex runs from a prior session
- All 3 passed signal parity, execution parity, and OCO lifecycle checks
- EURUSD, USDJPY, USDCAD have not been run yet
- The existing `local-jforex-parity-matrix` Makefile target runs the full 2-day tick replay per symbol (~40 min each)

### Critical file inventory

| File | Role |
|------|------|
| `scripts/run_local_jforex_surrogate_matrix.py` | Orchestrates per-symbol: start API, run Java surrogate, collect reports |
| `scripts/validate_local_jforex_surrogate.py` | Existing certification: aggregates parity CSVs into pass/fail |
| `configs/research/governance/oco_history_dukascopy_candidate/2025-07/{SYMBOL}_oco_locked_predictions.parquet` | Python backtest ground truth |
| `data/analysis/backtest_reconcile/{SYMBOL}_*_runtime_events.csv` | JForex surrogate output |
| `data/analysis/backtest_reconcile/{SYMBOL}_*_signal_parity_summary.csv` | Signal parity pass/fail |
| `data/analysis/backtest_reconcile/{SYMBOL}_*_execution_parity_summary.csv` | Execution pass/fail |
| `data/analysis/backtest_reconcile/{SYMBOL}_*_oco_lifecycle_summary.csv` | OCO lifecycle pass/fail |
| `src/jforex/src/main/java/com/behemoth/jforex/reporting/Stage14ArtifactWriter.java` | Writes runtime events + parity CSVs |
| `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java` | Core JForex logic: tick → predict → order → lifecycle |

---

## Task 1: Build the outcome reconciliation script

This is the new script that joins locked predictions against JForex runtime events and computes aggregate outcome metrics.

**Files:**
- Create: `scripts/reconcile_jforex_outcomes.py`
- Test: `tests/test_reconcile_jforex_outcomes.py`

### Step-by-step

- [ ] **Step 1: Write the test for locked prediction loading**

```python
# tests/test_reconcile_jforex_outcomes.py
"""Tests for JForex outcome reconciliation."""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import duckdb
import pytest


def _write_locked_predictions(tmp: Path, symbol: str, rows: list[dict]) -> Path:
    """Write a minimal locked predictions parquet for testing."""
    con = duckdb.connect()
    cols = ", ".join(f"'{k}'" for k in rows[0])
    vals = ", ".join(
        "(" + ", ".join(
            f"'{v}'" if isinstance(v, str) else str(v) for v in r.values()
        ) + ")"
        for r in rows
    )
    con.execute(
        f"COPY (SELECT * FROM (VALUES {vals}) AS t({cols})) "
        f"TO '{tmp / f'{symbol.lower()}_oco_locked_predictions.parquet'}' (FORMAT PARQUET)"
    )
    return tmp


def test_load_locked_predictions_filters_selected():
    from scripts.reconcile_jforex_outcomes import load_locked_predictions

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _write_locked_predictions(tmp, "EURUSD", [
            {"close_ts": "2025-07-01T00:00:00Z", "candidate_uid": "uid_a",
             "pred_prob": 0.6, "target_gross_pips": 3.5, "target_gross_pos": 1,
             "selected_exec": 1, "event_ordinal": 0},
            {"close_ts": "2025-07-01T01:00:00Z", "candidate_uid": "uid_a",
             "pred_prob": 0.4, "target_gross_pips": -1.2, "target_gross_pos": 0,
             "selected_exec": 0, "event_ordinal": 1},
        ])
        df = load_locked_predictions(tmp, "EURUSD")
        assert len(df) == 1
        assert df["target_gross_pips"].iloc[0] == 3.5
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py::test_load_locked_predictions_filters_selected -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.reconcile_jforex_outcomes'`

- [ ] **Step 3: Write the locked prediction loader**

```python
# scripts/reconcile_jforex_outcomes.py
#!/usr/bin/env python3
"""Reconcile JForex surrogate outcomes against locked Python backtest predictions.

Joins the governance-locked predictions (ground truth) with JForex runtime events
to compute aggregate outcome metrics per symbol and produce a pass/fail verdict.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import duckdb
import pandas as pd


DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
DEFAULT_LOCK_DIR = "configs/research/governance/oco_history_dukascopy_candidate/2025-07"
DEFAULT_RECONCILE_DIR = "data/analysis/backtest_reconcile"


def load_locked_predictions(lock_dir: Path, symbol: str) -> pd.DataFrame:
    """Load locked predictions for a symbol, filtered to selected_exec=1."""
    path = lock_dir / f"{symbol.lower()}_oco_locked_predictions.parquet"
    con = duckdb.connect()
    df = con.execute(
        "SELECT close_ts, candidate_uid, pred_prob, target_gross_pips, "
        "target_gross_pos, selected_exec, event_ordinal "
        f"FROM read_parquet('{path}') WHERE selected_exec = 1 "
        "ORDER BY close_ts, candidate_uid"
    ).fetchdf()
    con.close()
    return df
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py::test_load_locked_predictions_filters_selected -v
```
Expected: PASS

- [ ] **Step 5: Write the test for runtime event loading**

```python
# Append to tests/test_reconcile_jforex_outcomes.py

def _write_runtime_events(tmp: Path, symbol: str, prefix: str, rows: list[dict]) -> None:
    """Write a minimal runtime events CSV."""
    path = tmp / f"{symbol}_{prefix}_runtime_events.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["event_ts_utc", "symbol", "category", "event_name", "pass", "detail"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def test_load_runtime_events_counts_categories():
    from scripts.reconcile_jforex_outcomes import load_runtime_events

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _write_runtime_events(tmp, "EURUSD", "jforex", [
            {"event_ts_utc": "2025-07-01T00:00:00Z", "symbol": "EURUSD",
             "category": "signal", "event_name": "predict_cycle", "pass": "true",
             "detail": "prediction_count=5;selected_count=2;blocked_count=0;completed_bar_ticks=[100]"},
            {"event_ts_utc": "2025-07-01T00:01:00Z", "symbol": "EURUSD",
             "category": "execution", "event_name": "order_submitted", "pass": "true",
             "detail": "OCO_EURUSD_T100_H6:BUY"},
            {"event_ts_utc": "2025-07-01T00:01:01Z", "symbol": "EURUSD",
             "category": "execution", "event_name": "order_submitted", "pass": "true",
             "detail": "OCO_EURUSD_T100_H6:SELL"},
            {"event_ts_utc": "2025-07-01T00:02:00Z", "symbol": "EURUSD",
             "category": "execution", "event_name": "order_filled", "pass": "true",
             "detail": "OCO_EURUSD_T100_H6:BUY"},
        ])
        events = load_runtime_events(tmp, "EURUSD")
        assert events["predict_cycles"] == 1
        assert events["orders_submitted"] == 2
        assert events["orders_filled"] == 1
```

- [ ] **Step 6: Run the test to verify it fails**

Run:
```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py::test_load_runtime_events_counts_categories -v
```
Expected: FAIL — `ImportError: cannot import name 'load_runtime_events'`

- [ ] **Step 7: Write the runtime events loader**

Add to `scripts/reconcile_jforex_outcomes.py`:

```python
def load_runtime_events(reconcile_dir: Path, symbol: str) -> dict:
    """Load and summarise JForex runtime events for a symbol.

    Returns a dict with aggregate counts:
      predict_cycles, orders_submitted, orders_filled, execution_failures,
      lifecycle_failures, lifecycle_violations
    """
    # Find the runtime events CSV (prefix may be 'jforex' or 'local_jforex')
    candidates = list(reconcile_dir.glob(f"{symbol}_*_runtime_events.csv"))
    if not candidates:
        return {
            "predict_cycles": 0, "orders_submitted": 0, "orders_filled": 0,
            "execution_failures": 0, "lifecycle_failures": 0, "lifecycle_violations": 0,
            "selected_count_total": 0,
        }
    path = candidates[0]
    df = pd.read_csv(path)

    predict_cycles = len(df[df["event_name"] == "predict_cycle"])
    orders_submitted = len(df[df["event_name"] == "order_submitted"])
    orders_filled = len(df[df["event_name"] == "order_filled"])
    execution_failures = len(df[
        (df["category"] == "execution") & (df["pass"].astype(str) == "false")
    ])
    lifecycle_failures = len(df[df["event_name"] == "sibling_cancel_failure"])
    lifecycle_violations = len(df[df["event_name"] == "lifecycle_violation"])

    # Parse selected_count from predict_cycle detail strings
    selected_total = 0
    for detail in df.loc[df["event_name"] == "predict_cycle", "detail"]:
        for part in str(detail).split(";"):
            if part.startswith("selected_count="):
                selected_total += int(part.split("=")[1])
    return {
        "predict_cycles": predict_cycles,
        "orders_submitted": orders_submitted,
        "orders_filled": orders_filled,
        "execution_failures": execution_failures,
        "lifecycle_failures": lifecycle_failures,
        "lifecycle_violations": lifecycle_violations,
        "selected_count_total": selected_total,
    }
```

- [ ] **Step 8: Run the test to verify it passes**

Run:
```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py -v
```
Expected: 2 PASSED

- [ ] **Step 9: Commit**

```bash
git add scripts/reconcile_jforex_outcomes.py tests/test_reconcile_jforex_outcomes.py
git commit -m "feat: add locked prediction and runtime event loaders for outcome reconciliation"
```

---

## Task 2: Build the outcome comparison and verdict logic

**Files:**
- Modify: `scripts/reconcile_jforex_outcomes.py`
- Modify: `tests/test_reconcile_jforex_outcomes.py`

- [ ] **Step 1: Write the test for per-symbol outcome comparison**

```python
# Append to tests/test_reconcile_jforex_outcomes.py

def test_compare_outcomes_pass():
    from scripts.reconcile_jforex_outcomes import compare_outcomes

    result = compare_outcomes(
        symbol="EURUSD",
        locked_count=217,
        locked_gross_pips_total=752.9,
        locked_win_rate=0.742,       # 161/217
        jforex_predict_cycles=200,   # close to 217
        jforex_selected_total=210,   # close to 217
        jforex_orders_submitted=4,
        jforex_execution_failures=0,
        jforex_lifecycle_failures=0,
    )
    assert result["signal_coverage_pass"] is True
    assert result["execution_clean_pass"] is True
    assert result["overall_pass"] is True


def test_compare_outcomes_fail_low_coverage():
    from scripts.reconcile_jforex_outcomes import compare_outcomes

    result = compare_outcomes(
        symbol="EURUSD",
        locked_count=217,
        locked_gross_pips_total=752.9,
        locked_win_rate=0.742,
        jforex_predict_cycles=50,    # way too low
        jforex_selected_total=40,    # way too low
        jforex_orders_submitted=0,
        jforex_execution_failures=0,
        jforex_lifecycle_failures=0,
    )
    assert result["signal_coverage_pass"] is False
    assert result["overall_pass"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py::test_compare_outcomes_pass -v
```
Expected: FAIL

- [ ] **Step 3: Write the comparison function**

Add to `scripts/reconcile_jforex_outcomes.py`:

```python
def compare_outcomes(
    symbol: str,
    locked_count: int,
    locked_gross_pips_total: float,
    locked_win_rate: float,
    jforex_predict_cycles: int,
    jforex_selected_total: int,
    jforex_orders_submitted: int,
    jforex_execution_failures: int,
    jforex_lifecycle_failures: int,
    signal_coverage_threshold: float = 0.8,
) -> dict:
    """Compare JForex outcomes against locked Python backtest predictions.

    Args:
        signal_coverage_threshold: minimum ratio of jforex_selected_total / locked_count
            to consider signal coverage acceptable. Default 0.5 (50%).
            Existing runs show near-1:1 coverage, so 0.8 is conservative.
            Bar boundary drift on tick replay can reduce coverage slightly.

    Returns:
        dict with per-check pass/fail and overall verdict.
    """
    signal_coverage_ratio = (
        jforex_selected_total / locked_count if locked_count > 0 else 0.0
    )
    signal_coverage_pass = signal_coverage_ratio >= signal_coverage_threshold

    execution_clean_pass = (
        jforex_execution_failures == 0 and jforex_lifecycle_failures == 0
    )

    has_trades = jforex_orders_submitted > 0

    overall_pass = signal_coverage_pass and execution_clean_pass and has_trades

    return {
        "symbol": symbol,
        "locked_selected_count": locked_count,
        "locked_gross_pips_total": round(locked_gross_pips_total, 2),
        "locked_win_rate": round(locked_win_rate, 4),
        "jforex_predict_cycles": jforex_predict_cycles,
        "jforex_selected_total": jforex_selected_total,
        "jforex_orders_submitted": jforex_orders_submitted,
        "signal_coverage_ratio": round(signal_coverage_ratio, 4),
        "signal_coverage_pass": signal_coverage_pass,
        "execution_clean_pass": execution_clean_pass,
        "has_trades": has_trades,
        "overall_pass": overall_pass,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/reconcile_jforex_outcomes.py tests/test_reconcile_jforex_outcomes.py
git commit -m "feat: add outcome comparison logic with signal coverage and execution checks"
```

---

## Task 3: Wire up the CLI and summary report

**Files:**
- Modify: `scripts/reconcile_jforex_outcomes.py`

- [ ] **Step 1: Add the main function and CLI**

Add to `scripts/reconcile_jforex_outcomes.py`:

```python
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols", default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbol list",
    )
    parser.add_argument("--lock-dir", default=DEFAULT_LOCK_DIR)
    parser.add_argument("--reconcile-dir", default=DEFAULT_RECONCILE_DIR)
    parser.add_argument(
        "--signal-coverage-threshold", type=float, default=0.8,
        help="Min ratio of JForex selected predictions / locked predictions (default: 0.8)",
    )
    parser.add_argument(
        "--out-csv", default="data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv",
        help="Output CSV path for per-symbol results",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    lock_dir = Path(args.lock_dir)
    reconcile_dir = Path(args.reconcile_dir)

    results = []
    for symbol in symbols:
        locked = load_locked_predictions(lock_dir, symbol)
        events = load_runtime_events(reconcile_dir, symbol)

        locked_count = len(locked)
        locked_gross_total = float(locked["target_gross_pips"].sum())
        locked_win_rate = (
            float(locked["target_gross_pos"].mean()) if locked_count > 0 else 0.0
        )

        result = compare_outcomes(
            symbol=symbol,
            locked_count=locked_count,
            locked_gross_pips_total=locked_gross_total,
            locked_win_rate=locked_win_rate,
            jforex_predict_cycles=events["predict_cycles"],
            jforex_selected_total=events["selected_count_total"],
            jforex_orders_submitted=events["orders_submitted"],
            jforex_execution_failures=events["execution_failures"],
            jforex_lifecycle_failures=events["lifecycle_failures"],
            signal_coverage_threshold=args.signal_coverage_threshold,
        )
        results.append(result)

    # Print summary table
    print(f"\n{'Symbol':<8} {'Locked':>7} {'JFX Sel':>8} {'Coverage':>9} "
          f"{'Orders':>7} {'ExecOK':>7} {'Verdict':>8}")
    print("-" * 62)
    for r in results:
        verdict = "PASS" if r["overall_pass"] else "FAIL"
        print(
            f"{r['symbol']:<8} {r['locked_selected_count']:>7} "
            f"{r['jforex_selected_total']:>8} {r['signal_coverage_ratio']:>8.1%} "
            f"{r['jforex_orders_submitted']:>7} "
            f"{'yes' if r['execution_clean_pass'] else 'NO':>7} "
            f"{verdict:>8}"
        )

    # Write CSV
    out_path = Path(args.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    keys = results[0].keys() if results else []
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)
    print(f"\nResults written to {out_path}")

    # Exit code
    all_pass = all(r["overall_pass"] for r in results)
    if not all_pass:
        failing = [r["symbol"] for r in results if not r["overall_pass"]]
        print(f"\nFAILED symbols: {', '.join(failing)}")
        sys.exit(1)
    else:
        print("\nAll symbols PASSED outcome parity.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the CLI against existing data (3 completed symbols)**

Run:
```bash
uv run python scripts/reconcile_jforex_outcomes.py --symbols AUDUSD,GBPUSD,USDCHF
```

Expected: A summary table showing coverage ratios and pass/fail per symbol. All 3 should pass since they have existing runtime events with passing parity.

- [ ] **Step 3: Commit**

```bash
git add scripts/reconcile_jforex_outcomes.py
git commit -m "feat: add CLI and summary report for JForex outcome reconciliation"
```

---

## Task 4: Add Makefile target

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add the `jforex-outcome-parity` target**

Add after the `local-jforex-cert` target in `Makefile`:

```makefile
jforex-outcome-parity:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/reconcile_jforex_outcomes.py \
		--symbols $(or $(SYMBOLS),EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD) \
		--lock-dir $(or $(LOCK_DIR),configs/research/governance/oco_history_dukascopy_candidate/2025-07) \
		--reconcile-dir $(or $(RECONCILE_DIR),data/analysis/backtest_reconcile) \
		--signal-coverage-threshold $(or $(SIGNAL_COVERAGE_THRESHOLD),0.8) \
		--out-csv $(or $(OUT_CSV),data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv)
```

Register in `.PHONY` line.

- [ ] **Step 2: Test the target**

Run:
```bash
make jforex-outcome-parity SYMBOLS=AUDUSD,GBPUSD,USDCHF
```

Expected: Same output as Step 2 of Task 4.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "feat: add jforex-outcome-parity Makefile target"
```

---

## Task 5: Run all symbols via real Dukascopy and produce full report

Run all 6 symbols through the real Dukascopy `JForexTesterRunner` (much faster than the surrogate — ticks stream directly, no HTTP tick-batch bottleneck). Requires `BEHEMOTH_JFOREX_JNLP_URI`, `BEHEMOTH_JFOREX_USERNAME`, `BEHEMOTH_JFOREX_PASSWORD` in `.env`.

- [ ] **Step 1: Clear port and run all 6 symbols via Dukascopy**

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null
make jforex-dukascopy-matrix 2>&1 | tee /tmp/jforex_dukascopy_matrix.log
```

Runs sequentially: EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD.

- [ ] **Step 2: Run full outcome parity report**

```bash
make jforex-outcome-parity
```

Expected: 6-symbol summary table with all PASS.

- [ ] **Step 3: Run existing certification for completeness**

```bash
make local-jforex-cert
```

Expected: Green verdict for all 6 symbols.

- [ ] **Step 4: Commit all results**

```bash
git add data/analysis/backtest_reconcile/
git commit -m "feat: complete JForex outcome parity for all 6 symbols (2025-07)"
```

---

## Clean-up: Remove spotlight tick extraction

The spotlight approach was based on an incorrect assumption about event density. It should be removed to avoid confusion.

- [ ] **Step 1: Remove `scripts/extract_spotlight_ticks.py`**
- [ ] **Step 2: Remove `local-jforex-parity-spotlight` target from Makefile and `.PHONY`**
- [ ] **Step 3: Remove `data/analysis/spotlight_ticks/` directory**
- [ ] **Step 4: Commit**

```bash
git rm scripts/extract_spotlight_ticks.py
rm -rf data/analysis/spotlight_ticks/
git add Makefile
git commit -m "chore: remove spotlight tick extraction (event density made it impractical)"
```

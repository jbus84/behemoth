# Stage 14 Completion: Staleness Coverage, Event Disambiguation, and All-Green Snapshot

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three remaining code gaps in the JForex certification pipeline and produce an all-green Stage 14 snapshot for all 6 symbols.

**Architecture:** Three code tasks fix gaps in `reconcile_jforex_outcomes.py` and the `Makefile`; one execution task refreshes artifacts in the new 7-check format; one manual execution task (requiring Dukascopy credentials + 30–90 min) runs the real JForex tester for the 5 remaining symbols to achieve an all-green Stage 14.

**Tech Stack:** Python 3.12 (pytest, pandas, DuckDB), Make targets

---

## Gap Inventory

| Gap | Severity | Description |
|---|---|---|
| No `evaluated_at_utc` in outcome parity output | **P0** | Stage 14 staleness check can never fire on `jforex_outcome_parity_pass` — the 35-day gate is silently bypassed for the most important check |
| `load_runtime_events()` non-deterministic | **P0** | `glob("{symbol}_*_runtime_events.csv")` and `candidates[0]` will pick up local surrogate events instead of real tester events once both exist in the same directory after the real tester runs |
| No `full-stage14-cert` Makefile target | **P1** | Monthly recert requires 3 manual commands; easy to miss `jforex-outcome-parity` before `local-jforex-cert` |
| Stage 14 checks CSV in 5-check format | **P1** | Committed artifact is stale; needs regeneration with the 7-check schema added in the prior session |
| Real JForex tester not run (5/6 symbols) | **P0** | EURUSD, USDJPY, USDCHF, AUDUSD, USDCAD are red with `missing_inputs=4` each |

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/reconcile_jforex_outcomes.py` | **MODIFY** | Add `evaluated_at_utc` timestamp to aggregate and per-symbol CSV outputs; prefer real tester events over local surrogate events |
| `tests/test_reconcile_jforex_outcomes.py` | **MODIFY** | Add tests for `evaluated_at_utc` in output and real-over-local event file priority |
| `Makefile` | **MODIFY** | Add `full-stage14-cert` target (chains `jforex-outcome-parity` → `local-jforex-cert` → `stage14-jforex-cert`) |

---

### Task 1: Add `evaluated_at_utc` to Outcome Parity Output

**Context:** `scripts/reconcile_jforex_outcomes.py` writes `jforex_outcome_parity_summary.csv` (aggregate, read by Stage 14) and `{symbol}_local_jforex_outcome_parity_summary.csv` (per-symbol, read by `local-jforex-cert`). Neither file has an `evaluated_at_utc` column. Stage 14's staleness check (`max_artifact_age_days=35`) reads `evaluated_at_utc` from input CSVs; without it, `jforex_outcome_parity_pass` can never be flagged as stale. This makes the 35-day gate meaningless for the check most likely to drift after a model retrain.

The fix is to compute `now_utc` once in `main()` and attach it to every result dict before writing. `write_per_symbol_summaries()` writes `dict(r)` and will include `evaluated_at_utc` automatically. The aggregate CSV writing uses `keys = results[0].keys()` and will also include it.

**Files:**
- Modify: `scripts/reconcile_jforex_outcomes.py` (around lines 254–310)
- Modify: `tests/test_reconcile_jforex_outcomes.py` (add 2 new tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_reconcile_jforex_outcomes.py`:

```python
def test_reconcile_per_symbol_csv_includes_evaluated_at_utc(tmp_path):
    """Per-symbol output CSV must include a parseable evaluated_at_utc column."""
    from scripts.reconcile_jforex_outcomes import write_per_symbol_summaries
    import pandas as pd
    from datetime import datetime, timezone

    results = [
        {"symbol": "EURUSD", "overall_pass": True, "evaluated_at_utc": "2026-03-19T12:00:00Z"},
    ]
    write_per_symbol_summaries(results, out_dir=tmp_path)

    df = pd.read_csv(tmp_path / "EURUSD_local_jforex_outcome_parity_summary.csv")
    assert "evaluated_at_utc" in df.columns, "Per-symbol CSV missing evaluated_at_utc"
    ts = df["evaluated_at_utc"].iloc[0]
    # Must be parseable as UTC ISO-8601
    parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
```

```python
def test_reconcile_aggregate_csv_includes_evaluated_at_utc(tmp_path, monkeypatch):
    """Aggregate output CSV written by main() must include evaluated_at_utc for each symbol."""
    import pandas as pd
    import sys

    # Write minimal locked predictions and runtime events
    import duckdb, csv
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    reconcile_dir = tmp_path / "reconcile"
    reconcile_dir.mkdir()
    out_csv = tmp_path / "out.csv"

    # Minimal parquet: one selected prediction for EURUSD
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT '2025-07-07T12:00:00Z'::TIMESTAMPTZ AS close_ts, "
        "'uid_a' AS candidate_uid, 0.65 AS pred_prob, 3.5 AS target_gross_pips, "
        "1 AS target_gross_pos, 1 AS selected_exec, 0 AS event_ordinal) "
        f"TO '{lock_dir / 'eurusd_oco_locked_predictions.parquet'}' (FORMAT PARQUET)"
    )
    con.close()

    # Minimal runtime events
    events_path = reconcile_dir / "EURUSD_jforex_runtime_events.csv"
    with open(events_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["event_ts_utc", "symbol", "category", "event_name", "pass", "detail"],
        )
        writer.writeheader()
        writer.writerow({
            "event_ts_utc": "2025-07-07T12:00:00Z", "symbol": "EURUSD",
            "category": "signal", "event_name": "predict_cycle", "pass": "true",
            "detail": "selected_count=1",
        })
        writer.writerow({
            "event_ts_utc": "2025-07-07T12:01:00Z", "symbol": "EURUSD",
            "category": "execution", "event_name": "order_submitted", "pass": "true",
            "detail": "OCO_EURUSD_T100_H6_TS20250707120000_RIDNA_CID001:BUY",
        })

    monkeypatch.setattr(
        sys, "argv",
        [
            "reconcile_jforex_outcomes.py",
            "--symbols", "EURUSD",
            "--lock-dir", str(lock_dir),
            "--reconcile-dir", str(reconcile_dir),
            "--out-csv", str(out_csv),
        ],
    )
    from scripts.reconcile_jforex_outcomes import main
    try:
        main()
    except SystemExit:
        pass  # exit code 0 or 1 is fine; we just need the CSV written

    df = pd.read_csv(out_csv)
    assert "evaluated_at_utc" in df.columns, "Aggregate CSV missing evaluated_at_utc"
    ts = df["evaluated_at_utc"].iloc[0]
    from datetime import datetime
    parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py -k "evaluated_at_utc" -v 2>&1 | tail -15
```

Expected: 1 test FAILS — `test_reconcile_aggregate_csv_includes_evaluated_at_utc` (calls `main()` which doesn't yet emit `evaluated_at_utc`). `test_reconcile_per_symbol_csv_includes_evaluated_at_utc` will **pass** even before the fix because it injects `evaluated_at_utc` directly into the result dict passed to `write_per_symbol_summaries`. This is intentional — it tests the write path, not the `main()` injection. Only the aggregate test is the red-green gate.

- [ ] **Step 3: Add `evaluated_at_utc` to `reconcile_jforex_outcomes.py`**

In `main()` (around line 254), compute `now_utc` immediately before the symbol loop and attach it to every result:

```python
def main() -> None:
    args = _parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    lock_dir = Path(args.lock_dir)
    reconcile_dir = Path(args.reconcile_dir)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")   # ADD THIS LINE

    results = []
    for symbol in symbols:
        locked = load_locked_predictions(lock_dir, symbol, eval_start=args.eval_start, eval_end=args.eval_end)
        events = load_runtime_events(reconcile_dir, symbol)
        # ... existing code ...
        result = compare_outcomes(
            symbol=symbol,
            # ... existing args ...
        )
        result["evaluated_at_utc"] = now_utc    # ADD THIS LINE
        results.append(result)
```

The `now_utc` is computed once per `main()` invocation so all symbols in the same run share the same timestamp. `write_per_symbol_summaries()` already does `dict(r)` which will include `evaluated_at_utc`. The aggregate CSV uses `keys = results[0].keys()` which will also include it.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py -k "evaluated_at_utc" -v 2>&1 | tail -15
```

Expected: 2 tests PASS.

- [ ] **Step 5: Run full reconcile test suite to confirm no regressions**

```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py -v 2>&1 | tail -20
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/reconcile_jforex_outcomes.py tests/test_reconcile_jforex_outcomes.py
git commit -m "feat: add evaluated_at_utc to reconcile_jforex_outcomes outputs for Stage 14 staleness gate"
```

---

### Task 2: Fix `load_runtime_events()` to Prefer Real Tester Events

**Context:** After running the real Dukascopy JForex tester, the `data/analysis/backtest_reconcile/` directory contains both `{symbol}_jforex_runtime_events.csv` (real tester) and `{symbol}_local_jforex_runtime_events.csv` (local surrogate). `load_runtime_events()` currently does `glob(f"{symbol}_*_runtime_events.csv")` which matches both and takes `candidates[0]`. Python's `glob` sorts lexicographically — `EURUSD_jforex_runtime_events.csv` < `EURUSD_local_jforex_runtime_events.csv` alphabetically, so it would happen to pick the right one. But this is fragile and wrong by design: the correct behaviour must be explicit. Running `jforex-outcome-parity` after the real tester should always use real tester events, not local surrogate events.

The fix: check for the preferred real tester filename first (`{symbol}_jforex_runtime_events.csv`); fall back to the glob only if it doesn't exist.

**Files:**
- Modify: `scripts/reconcile_jforex_outcomes.py` (lines 75–92, `load_runtime_events()`)
- Modify: `tests/test_reconcile_jforex_outcomes.py` (add 1 new test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_reconcile_jforex_outcomes.py`:

```python
def test_load_runtime_events_prefers_real_over_local(tmp_path):
    """When both real-tester and local-surrogate event files exist, prefer the real one."""
    from scripts.reconcile_jforex_outcomes import load_runtime_events
    import csv

    # Real tester file: 5 predict_cycles
    real_path = tmp_path / "EURUSD_jforex_runtime_events.csv"
    with open(real_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["event_ts_utc", "symbol", "category", "event_name", "pass", "detail"],
        )
        writer.writeheader()
        for _ in range(5):
            writer.writerow({
                "event_ts_utc": "2025-07-07T12:00:00Z", "symbol": "EURUSD",
                "category": "signal", "event_name": "predict_cycle", "pass": "true",
                "detail": "selected_count=1",
            })

    # Local surrogate file: 99 predict_cycles (must NOT be selected)
    local_path = tmp_path / "EURUSD_local_jforex_runtime_events.csv"
    with open(local_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["event_ts_utc", "symbol", "category", "event_name", "pass", "detail"],
        )
        writer.writeheader()
        for _ in range(99):
            writer.writerow({
                "event_ts_utc": "2025-07-07T12:00:00Z", "symbol": "EURUSD",
                "category": "signal", "event_name": "predict_cycle", "pass": "true",
                "detail": "selected_count=1",
            })

    events = load_runtime_events(tmp_path, "EURUSD")
    assert events["predict_cycles"] == 5, (
        f"Expected 5 cycles from real tester file, got {events['predict_cycles']}. "
        "load_runtime_events() must prefer {symbol}_jforex_runtime_events.csv over "
        "{symbol}_local_jforex_runtime_events.csv."
    )
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py::test_load_runtime_events_prefers_real_over_local -v 2>&1 | tail -15
```

Expected: FAIL or PASS depending on lexicographic ordering. The test is written so the real file has 5 cycles and local has 99 — if the current code happens to pick the right one alphabetically the test may pass by accident. In that case confirm the logic is still wrong by temporarily renaming the real file to `EURUSD_zforex_runtime_events.csv` in the test and re-running — it must then pick up 99 (showing the bug). The fix must be explicit, not rely on sort order.

- [ ] **Step 3: Fix `load_runtime_events()` in `scripts/reconcile_jforex_outcomes.py`**

Current code (lines 75–92):
```python
def load_runtime_events(reconcile_dir: Path, symbol: str) -> dict:
    candidates = list(reconcile_dir.glob(f"{symbol}_*_runtime_events.csv"))
    if not candidates:
        return {
            "predict_cycles": 0, ...
        }
    path = candidates[0]
    df = pd.read_csv(path)
```

Replace the first three lines of the body with:
```python
def load_runtime_events(reconcile_dir: Path, symbol: str) -> dict:
    # Prefer real Dukascopy tester events ({symbol}_jforex_runtime_events.csv) over
    # local surrogate events ({symbol}_local_jforex_runtime_events.csv). Once a symbol
    # has been run through the real tester, jforex-outcome-parity must use those events.
    preferred = reconcile_dir / f"{symbol}_jforex_runtime_events.csv"
    if preferred.exists():
        candidates = [preferred]
    else:
        candidates = list(reconcile_dir.glob(f"{symbol}_*_runtime_events.csv"))
    if not candidates:
        return {
            "predict_cycles": 0, "orders_submitted": 0, "orders_filled": 0,
            "execution_failures": 0, "lifecycle_failures": 0, "lifecycle_violations": 0,
            "selected_count_total": 0,
            "submitted_group_close_ts_count": 0,
            "completed_group_count": 0,
            "submitted_group_close_ts": [],
        }
    path = candidates[0]
    df = pd.read_csv(path)
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py::test_load_runtime_events_prefers_real_over_local -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Run full reconcile test suite**

```bash
uv run pytest tests/test_reconcile_jforex_outcomes.py -v 2>&1 | tail -20
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/reconcile_jforex_outcomes.py tests/test_reconcile_jforex_outcomes.py
git commit -m "fix: load_runtime_events prefers real tester events over local surrogate events"
```

---

### Task 3: Add `full-stage14-cert` Convenience Makefile Target

**Context:** The monthly recertification procedure requires three Makefile commands in a specific order:
1. `make jforex-outcome-parity` — reconcile locked predictions against runtime events
2. `make local-jforex-cert` — aggregate per-symbol local surrogate results (reads per-symbol CSVs written by step 1)
3. `make stage14-jforex-cert` — build Stage 14 gate artifact (reads `local_jforex_surrogate_summary.csv` written by step 2)

Missing any step, or running them out of order, silently produces a stale cert. A `full-stage14-cert` target encodes this dependency explicitly and makes the monthly recert a single command.

Note: `jforex-dukascopy-matrix` (the real tester run) is intentionally NOT included because it is a long-running (30–90 min) credentialed operation that must be triggered deliberately.

**Files:**
- Modify: `Makefile` (`.PHONY` list + target definition + help text)

- [ ] **Step 1: Read the current `.PHONY` line and `help` target**

Confirm the `.PHONY` line and help target location in `Makefile`.

```bash
grep -n "full-stage14-cert\|local-jforex-cert\|stage14-jforex-cert" Makefile | head -15
```

- [ ] **Step 2: Add `full-stage14-cert` to `.PHONY`**

Find the `.PHONY` line (line 14) and add `full-stage14-cert` to the list alongside `stage14-jforex-cert`:

```makefile
.PHONY: ... local-jforex-cert stage14-jforex-cert full-stage14-cert ...
```

- [ ] **Step 3: Add the target definition**

Add immediately after the `stage14-jforex-cert` target (currently ends around line 615):

```makefile
full-stage14-cert: jforex-outcome-parity local-jforex-cert stage14-jforex-cert
```

This encodes the dependency order: outcome parity → local cert → Stage 14 cert. Make will run them sequentially because they are listed as prerequisites. Each target exits non-zero on failure, so `full-stage14-cert` stops at the first failure.

- [ ] **Step 4: Add help entry**

Find the help target (starts around line 687) and locate the `stage14-jforex-cert` help line (around line 725). Add immediately after it:

```makefile
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "full-stage14-cert" "Run outcome-parity → local-jforex-cert → stage14-jforex-cert in order (monthly recert command)"
```

Add it immediately after the `stage14-jforex-cert` help line.

- [ ] **Step 5: Verify the target runs (with existing artifacts)**

```bash
make full-stage14-cert 2>&1 | tail -20
```

Expected: Runs all three targets sequentially. Stage 14 will still be red for 5 symbols (missing real tester artifacts) but the target should complete without crashing.

- [ ] **Step 6: Commit**

```bash
git add Makefile
git commit -m "feat: add full-stage14-cert Makefile target for monthly recertification"
```

---

### Task 4: Refresh Stage 14 Artifacts to 7-Check Format

**Context:** The committed `stage14_jforex_runtime_certification_checks.csv` was generated before the previous session added the `jforex_outcome_parity_pass` and `local_jforex_surrogate_pass` checks. It shows only 5 checks per symbol for GBPUSD, and `missing_inputs=4` for other symbols in the old format. After Tasks 1–3, re-running `make full-stage14-cert` will regenerate artifacts with:
- 7 checks per symbol
- `evaluated_at_utc` timestamps in `jforex_outcome_parity_summary.csv`
- Correct real-vs-local event disambiguation (no change for current data since real tester only has GBPUSD)
- Current timestamps on all artifact files

This task requires no code changes — it is a pure execution task.

**Files:**
- Regenerated: `data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv`
- Regenerated: `data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv`
- Regenerated: `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv`
- Regenerated: `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`
- Regenerated: `docs/analysis/stage14_jforex_runtime_certification_report.md`
- Regenerated: `docs/strategy_bible/generated/stage_14_snapshot.md`

- [ ] **Step 1: Run `make full-stage14-cert`**

```bash
make full-stage14-cert 2>&1 | tee /tmp/full_stage14_cert.log
```

Expected output pattern:
```
All symbols PASSED outcome parity.
...
Stage 14 cert: GBPUSD=green, EURUSD=red(missing_inputs=4), ...
```

GBPUSD should be green (7/7 checks). Other 5 symbols should be red with `missing_inputs=4` (the 4 real-tester-specific checks are missing).

- [ ] **Step 2: Verify GBPUSD now shows 7 checks**

```bash
python3 -c "
import pandas as pd
df = pd.read_csv('data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv')
print('GBPUSD checks:')
print(df[df['symbol']=='GBPUSD'][['metric_name','status','details']].to_string())
print(f'\nTotal checks for GBPUSD: {len(df[df[\"symbol\"]==\"GBPUSD\"])}')
"
```

Expected: 7 rows for GBPUSD, all `status=pass`.

- [ ] **Step 3: Verify `evaluated_at_utc` is now in `jforex_outcome_parity_summary.csv`**

```bash
python3 -c "
import pandas as pd
df = pd.read_csv('data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv')
print(df[['symbol','evaluated_at_utc','overall_pass']].to_string())
"
```

Expected: All 6 symbols present with non-empty `evaluated_at_utc` timestamp.

- [ ] **Step 4: Commit the refreshed artifacts**

```bash
git add \
  data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv \
  data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv \
  data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv \
  data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv \
  docs/analysis/stage14_jforex_runtime_certification_report.md \
  docs/strategy_bible/generated/stage_14_snapshot.md
git commit -m "cert: refresh Stage 14 artifacts to 7-check format with evaluated_at_utc timestamps"
```

---

### Task 5: Run Real JForex Tester for 5 Remaining Symbols and Produce All-Green Stage 14

**Context:** Stage 14 is currently red for EURUSD, USDJPY, USDCHF, AUDUSD, USDCAD because the real Dukascopy JForex tester has not been run for those symbols. The 4 missing checks per symbol are: `jforex_signal_parity_pass`, `jforex_execution_parity_pass`, `oco_lifecycle_pass`, `operational_ready_pass` — all require real Dukascopy broker/tester output. This task requires:

- Real Dukascopy credentials: `JFOREX_LOGIN`, `JFOREX_PASSWORD`
- ~30–90 min of tester runtime (tick download + replay for 5 symbols sequentially)
- The strategy models and locked predictions must be for the same evaluation window (July 7–9, 2025, model month 2025-07)

**Files:**
- No code changes. Executes existing Makefile targets.
- Produces: real tester artifacts for 5 symbols + all-green `stage14_jforex_runtime_certification_summary.csv`

- [ ] **Step 1: Verify Dukascopy credentials and evaluation window**

```bash
echo "JFOREX_LOGIN=${JFOREX_LOGIN:-NOT_SET}"
echo "JFOREX_PASSWORD=${JFOREX_PASSWORD:-NOT_SET}"
```

Expected: Both set. If not, obtain credentials before proceeding.

Also confirm the model month and evaluation window match the Makefile defaults:
- `START_TS=2025-07-07T00:00:00Z`
- `END_TS=2025-07-09T00:00:00Z`
- `MODEL_MONTH=2025-07`

- [ ] **Step 2: Confirm local surrogate cert is all-green**

```bash
python3 -c "
import pandas as pd
df = pd.read_csv('data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv')
print(df[['symbol','verdict','local_jforex_surrogate_pass']].to_string())
all_green = all(df['verdict'] == 'green')
print('All green:', all_green)
"
```

Expected: All 6 symbols green. This confirms the Python API and Java core are in sync before the real tester run.

- [ ] **Step 3: Run the real JForex tester for the 5 remaining symbols**

```bash
make jforex-dukascopy-matrix SYMBOLS="EURUSD,USDJPY,USDCHF,AUDUSD,USDCAD" 2>&1 | tee /tmp/jforex_matrix_run.log
```

Expected runtime: 30–90 minutes. Monitor `/tmp/jforex_matrix_run.log` for errors. When complete, verify the real tester artifacts exist:

```bash
for sym in EURUSD USDJPY USDCHF AUDUSD USDCAD; do
  echo -n "$sym signal: "
  ls data/analysis/backtest_reconcile/${sym}_jforex_signal_parity_summary.csv 2>/dev/null && echo "OK" || echo "MISSING"
done
```

- [ ] **Step 4: Run full Stage 14 certification pipeline**

```bash
make full-stage14-cert 2>&1 | tee /tmp/full_stage14_final.log
```

This runs:
1. `jforex-outcome-parity` — re-reconciles predictions against runtime events. With Task 2's fix, for each symbol that now has `{symbol}_jforex_runtime_events.csv`, the real tester events will be used.
2. `local-jforex-cert` — rebuilds `local_jforex_surrogate_summary.csv` with fresh timestamps.
3. `stage14-jforex-cert` — builds the final Stage 14 cert with all 7 checks.

- [ ] **Step 5: Verify all-green Stage 14**

```bash
python3 -c "
import pandas as pd
df = pd.read_csv('data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv')
print(df[['symbol','verdict','missing_inputs','stage14_jforex_cert_pass']].to_string())
all_green = all(df['verdict'] == 'green')
print()
print('ALL GREEN:', all_green)
"
```

Expected:
```
   symbol verdict  missing_inputs  stage14_jforex_cert_pass
0  AUDUSD   green               0                      True
1  EURUSD   green               0                      True
2  GBPUSD   green               0                      True
3  USDCAD   green               0                      True
4  USDCHF   green               0                      True
5  USDJPY   green               0                      True

ALL GREEN: True
```

- [ ] **Step 6: Commit the all-green Stage 14 snapshot**

```bash
git add \
  data/analysis/backtest_reconcile/EURUSD_jforex_signal_parity_summary.csv \
  data/analysis/backtest_reconcile/EURUSD_jforex_execution_parity_summary.csv \
  data/analysis/backtest_reconcile/EURUSD_jforex_oco_lifecycle_summary.csv \
  data/analysis/backtest_reconcile/EURUSD_jforex_operational_ready_summary.csv \
  data/analysis/backtest_reconcile/EURUSD_jforex_runtime_events.csv \
  data/analysis/backtest_reconcile/USDJPY_jforex_signal_parity_summary.csv \
  data/analysis/backtest_reconcile/USDJPY_jforex_execution_parity_summary.csv \
  data/analysis/backtest_reconcile/USDJPY_jforex_oco_lifecycle_summary.csv \
  data/analysis/backtest_reconcile/USDJPY_jforex_operational_ready_summary.csv \
  data/analysis/backtest_reconcile/USDJPY_jforex_runtime_events.csv \
  data/analysis/backtest_reconcile/USDCHF_jforex_signal_parity_summary.csv \
  data/analysis/backtest_reconcile/USDCHF_jforex_execution_parity_summary.csv \
  data/analysis/backtest_reconcile/USDCHF_jforex_oco_lifecycle_summary.csv \
  data/analysis/backtest_reconcile/USDCHF_jforex_operational_ready_summary.csv \
  data/analysis/backtest_reconcile/USDCHF_jforex_runtime_events.csv \
  data/analysis/backtest_reconcile/AUDUSD_jforex_signal_parity_summary.csv \
  data/analysis/backtest_reconcile/AUDUSD_jforex_execution_parity_summary.csv \
  data/analysis/backtest_reconcile/AUDUSD_jforex_oco_lifecycle_summary.csv \
  data/analysis/backtest_reconcile/AUDUSD_jforex_operational_ready_summary.csv \
  data/analysis/backtest_reconcile/AUDUSD_jforex_runtime_events.csv \
  data/analysis/backtest_reconcile/USDCAD_jforex_signal_parity_summary.csv \
  data/analysis/backtest_reconcile/USDCAD_jforex_execution_parity_summary.csv \
  data/analysis/backtest_reconcile/USDCAD_jforex_oco_lifecycle_summary.csv \
  data/analysis/backtest_reconcile/USDCAD_jforex_operational_ready_summary.csv \
  data/analysis/backtest_reconcile/USDCAD_jforex_runtime_events.csv \
  data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv \
  data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv \
  data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv \
  data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv \
  data/analysis/backtest_reconcile/*_local_jforex_outcome_parity_summary.csv \
  docs/analysis/stage14_jforex_runtime_certification_report.md \
  docs/strategy_bible/generated/stage_14_snapshot.md
git commit -m "cert: Stage 14 all-green snapshot for all 6 symbols — real JForex tester certified"
```

---

## Completion Checklist

Before declaring Stage 14 complete:

- [ ] `uv run pytest tests/test_reconcile_jforex_outcomes.py -v` — all tests pass (includes `evaluated_at_utc` and real-vs-local event preference tests)
- [ ] `uv run pytest tests/ -x -q` — full Python test suite clean
- [ ] `make jforex-outcome-parity` — all 6 symbols pass with `evaluated_at_utc` in aggregate CSV
- [ ] `make local-jforex-cert` — all 6 symbols green
- [ ] `make stage14-jforex-cert` — all 6 symbols green, 7 checks each, `missing_inputs=0`
- [ ] `make full-stage14-cert` — runs end-to-end without errors
- [ ] `docs/strategy_bible/generated/stage_14_snapshot.md` committed with all-green results

## Monthly Recertification Runbook

After each model retrain (monthly), to recertify Stage 14:

```bash
# 1. Run real JForex tester for all symbols (requires credentials, ~30-90 min)
make jforex-dukascopy-matrix SYMBOLS="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD"

# 2. Run full certification pipeline (outcome parity → local cert → stage14)
make full-stage14-cert

# 3. Verify all green
python3 -c "
import pandas as pd
df = pd.read_csv('data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv')
print(df[['symbol','verdict','missing_inputs']].to_string())
print('ALL GREEN:', all(df['verdict'] == 'green'))
"

# 4. Commit artifacts
git add data/analysis/backtest_reconcile/ docs/strategy_bible/generated/stage_14_snapshot.md
git commit -m "cert: Stage 14 recertification for model month YYYY-MM"
```

**Staleness reminder:** The 35-day staleness gate means artifacts must be regenerated within 35 days of the previous run. A monthly retrain on the 1st of each month means the cert must be re-run by the 5th of the following month.

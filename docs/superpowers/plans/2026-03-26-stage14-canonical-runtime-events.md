# Stage 14 Canonical Runtime Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Stage 14 outcome reconciliation read only canonical `{symbol}_jforex_runtime_events.csv` artifacts, fail hard when they are missing or malformed, and ignore local surrogate runtime-event files for this path.

**Architecture:** Keep the existing reconciliation math and event parsing logic, but replace wildcard runtime-event selection with explicit canonical path resolution plus schema validation. This isolates JForex tester parity from local surrogate artifacts and turns the current ambiguous `KeyError: 'detail'` failure into deterministic, actionable errors.

**Tech Stack:** Python 3.12, pandas, pytest, existing Stage 14 reconciliation scripts

---

### Task 1: Lock Down Canonical Runtime-Event Selection With Tests

**Files:**
- Modify: `tests/test_reconcile_jforex_outcomes.py`
- Reference: `scripts/reconcile_jforex_outcomes.py`

- [ ] **Step 1: Add a failing test proving canonical JForex runtime-events are preferred**

Add a test that creates both runtime-event files for one symbol and asserts the JForex file drives the result:

```python
def test_load_runtime_events_prefers_canonical_jforex_file(tmp_path: Path) -> None:
    reconcile_dir = tmp_path
    pd.DataFrame(
        [
            {
                "event_ts_utc": "2026-02-07T00:00:00Z",
                "symbol": "EURUSD",
                "category": "predict",
                "event_name": "predict_cycle",
                "pass": True,
                "detail": "selected_count=2;blocked_count=0",
            }
        ]
    ).to_csv(reconcile_dir / "EURUSD_jforex_runtime_events.csv", index=False)
    pd.DataFrame(
        [
            {
                "event_ts_utc": "2026-02-07T00:00:00Z",
                "symbol": "EURUSD",
                "category": "predict",
                "event_name": "predict_cycle",
                "pass": True,
                "detail": "selected_count=99;blocked_count=0",
            }
        ]
    ).to_csv(reconcile_dir / "EURUSD_local_jforex_runtime_events.csv", index=False)

    result = load_runtime_events("EURUSD", reconcile_dir)

    assert result["selected_count_total"] == 2
```

- [ ] **Step 2: Add a failing test proving malformed local surrogate files do not poison JForex outcome parity**

Add a test where the local file is malformed but the canonical JForex file is valid:

```python
def test_load_runtime_events_ignores_malformed_local_surrogate_file(tmp_path: Path) -> None:
    reconcile_dir = tmp_path
    pd.DataFrame(
        [
            {
                "event_ts_utc": "2026-02-07T00:00:00Z",
                "symbol": "GBPUSD",
                "category": "predict",
                "event_name": "predict_cycle",
                "pass": True,
                "detail": "selected_count=1;blocked_count=0",
            }
        ]
    ).to_csv(reconcile_dir / "GBPUSD_jforex_runtime_events.csv", index=False)
    pd.DataFrame([{"broken": 1}]).to_csv(
        reconcile_dir / "GBPUSD_local_jforex_runtime_events.csv",
        index=False,
    )

    result = load_runtime_events("GBPUSD", reconcile_dir)

    assert result["selected_count_total"] == 1
```

- [ ] **Step 3: Add failing tests for strict missing-file and missing-column errors**

Add tests for the strict contract:

```python
def test_load_runtime_events_fails_when_canonical_file_is_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="missing runtime events file"):
        load_runtime_events("USDJPY", tmp_path)


def test_load_runtime_events_fails_when_canonical_file_is_missing_detail_column(tmp_path: Path) -> None:
    pd.DataFrame(
        [
            {
                "event_ts_utc": "2026-02-07T00:00:00Z",
                "symbol": "USDJPY",
                "category": "predict",
                "event_name": "predict_cycle",
                "pass": True,
            }
        ]
    ).to_csv(tmp_path / "USDJPY_jforex_runtime_events.csv", index=False)

    with pytest.raises(SystemExit, match="missing columns \\[detail\\]"):
        load_runtime_events("USDJPY", tmp_path)
```

- [ ] **Step 4: Run the targeted tests to verify they fail for the right reasons**

Run:

```bash
uv run pytest -q tests/test_reconcile_jforex_outcomes.py
```

Expected before implementation:
- the new tests fail
- failure mentions missing canonical-file handling or wildcard-based selection behavior

- [ ] **Step 5: Commit the red tests**

```bash
git add tests/test_reconcile_jforex_outcomes.py
git commit -m "test: define stage14 canonical runtime event contract"
```

### Task 2: Implement Canonical Selection and Schema Validation

**Files:**
- Modify: `scripts/reconcile_jforex_outcomes.py`
- Test: `tests/test_reconcile_jforex_outcomes.py`

- [ ] **Step 1: Add explicit canonical runtime-event path resolution**

Introduce a helper near `load_runtime_events(...)`:

```python
REQUIRED_RUNTIME_EVENT_COLUMNS = ("event_name", "category", "pass", "detail")


def canonical_runtime_events_path(reconcile_dir: Path, symbol: str) -> Path:
    return reconcile_dir / f"{symbol}_jforex_runtime_events.csv"
```

- [ ] **Step 2: Add schema validation with strict error messages**

Add a validator that checks both existence and required columns:

```python
def load_runtime_events_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"missing runtime events file: {path}")
    df = pd.read_csv(path)
    missing = [col for col in REQUIRED_RUNTIME_EVENT_COLUMNS if col not in df.columns]
    if missing:
        cols = ",".join(missing)
        raise SystemExit(f"runtime events file missing columns [{cols}]: {path}")
    return df
```

- [ ] **Step 3: Replace wildcard discovery in `load_runtime_events(...)`**

Update the start of the function from wildcard selection to the canonical path:

```python
path = canonical_runtime_events_path(Path(reconcile_dir), symbol)
df = load_runtime_events_frame(path)
```

Delete the old wildcard block:

```python
candidates = list(reconcile_dir.glob(f"{symbol}_*_runtime_events.csv"))
...
path = candidates[0]
df = pd.read_csv(path)
```

- [ ] **Step 4: Keep the downstream parsing logic unchanged**

Do not redesign event parsing in this task. The point is deterministic input selection and explicit validation, not metric semantics changes.

- [ ] **Step 5: Run the targeted tests to verify the contract now passes**

Run:

```bash
uv run pytest -q tests/test_reconcile_jforex_outcomes.py
```

Expected:
- all tests in `tests/test_reconcile_jforex_outcomes.py` pass

- [ ] **Step 6: Commit the implementation**

```bash
git add scripts/reconcile_jforex_outcomes.py tests/test_reconcile_jforex_outcomes.py
git commit -m "fix: require canonical jforex runtime events in stage14"
```

### Task 3: Re-Run Certification Verification

**Files:**
- Verify: `scripts/reconcile_jforex_outcomes.py`
- Verify outputs: `data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv`

- [ ] **Step 1: Re-run Stage 14 directly**

Run:

```bash
make full-stage14-cert \
  LOCK_DIR=configs/research/governance/oco_history_dukascopy_candidate/2026-02 \
  EVAL_START=2026-02-07T00:00:00Z \
  EVAL_END=2026-02-09T00:00:00Z
```

Expected:
- `jforex-outcome-parity` no longer crashes with `KeyError: 'detail'`
- Stage 14 either passes or fails on actual parity results

- [ ] **Step 2: Re-run the full monthly gate on the alternate port range**

Run:

```bash
API_PORT=8010 METRICS_PORT_BASE=9480 uv run python scripts/run_monthly_recert.py --model-month 2026-02
```

Expected:
- the run clears sync, Dukascopy matrix, local surrogate parity, and Stage 14 parsing
- any remaining failure is a real certification/parity issue, not artifact ambiguity

- [ ] **Step 3: Inspect the certification outputs**

Review:

```bash
sed -n '1,40p' data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv
sed -n '1,80p' data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv
```

Expected:
- no parser crash
- explicit per-symbol pass/fail rows

- [ ] **Step 4: Commit only if code or intended tracked artifacts changed**

If only code/tests changed:

```bash
git add scripts/reconcile_jforex_outcomes.py tests/test_reconcile_jforex_outcomes.py
git commit -m "fix: tighten stage14 runtime event selection"
```

If tracked certification artifacts were intentionally refreshed, review them first and include only the files that belong in repo history.

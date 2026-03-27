# Stage 14 Canonical Runtime Events Design

## Context

`make monthly-recert MODEL_MONTH=2026-02` now clears candidate sync, the Dukascopy JForex matrix, and the local surrogate parity matrix. The current failure is in Stage 14 outcome reconciliation:

- `scripts/reconcile_jforex_outcomes.py`
- `load_runtime_events(...)`
- `KeyError: 'detail'`

The current loader discovers runtime event files with a wildcard:

- `reconcile_dir.glob(f"{symbol}_*_runtime_events.csv")`
- then takes `candidates[0]`

That makes Stage 14 depend on filesystem ordering and mixed artifact types in `data/analysis/backtest_reconcile/`. The directory contains both:

- `{symbol}_jforex_runtime_events.csv`
- `{symbol}_local_jforex_runtime_events.csv`

For a definitive certification gate, wildcard selection is too ambiguous. Stage 14 must read the exact artifact type it intends to validate.

## Goal

Make Stage 14 outcome parity consume only the canonical JForex tester runtime-events artifact for each symbol, fail hard when that artifact is missing or malformed, and ignore local surrogate runtime-event files entirely for this path.

## Non-Goals

- Redesigning the event schema
- Changing the meaning of existing parity metrics
- Introducing a run-manifest system
- Making reconciliation tolerant of missing canonical Stage 14 artifacts

## Recommended Approach

Replace wildcard runtime-event discovery in `scripts/reconcile_jforex_outcomes.py` with explicit canonical path resolution:

- `reconcile_dir / f"{symbol}_jforex_runtime_events.csv"`

Then validate that file’s schema before any event parsing.

This is the smallest correct fix because:

- the canonical file naming already exists
- Stage 14 outcome parity is specifically about the JForex tester artifact, not local surrogate artifacts
- deterministic artifact selection is required for a definitive release gate

## Contract Changes

### Canonical File Selection

For Stage 14 outcome parity, the loader must read exactly:

- `{symbol}_jforex_runtime_events.csv`

It must not use wildcard selection and must not treat any other runtime-events file as a substitute.

### Required Schema

The canonical file must contain these columns:

- `event_name`
- `category`
- `pass`
- `detail`

These are the columns the current reconciliation logic depends on.

### Strict Failure Policy

If the canonical file is missing, Stage 14 must fail hard.

If the canonical file exists but is missing required columns, Stage 14 must fail hard.

There is no zero-summary fallback for missing canonical JForex runtime-events artifacts.

### Local Surrogate Isolation

Files such as `{symbol}_local_jforex_runtime_events.csv` must be ignored by Stage 14 JForex outcome parity. They remain valid inputs for local surrogate validation only.

## Implementation Design

### `scripts/reconcile_jforex_outcomes.py`

Add a small canonical artifact resolver for JForex runtime events:

- input: `reconcile_dir`, `symbol`
- output: `Path(reconcile_dir) / f"{symbol}_jforex_runtime_events.csv"`

Add a schema validator for runtime-events CSVs that:

1. reads the file
2. verifies the required columns are present
3. raises a precise error if any are missing

Then keep the existing filtering and parsing logic unchanged after validation.

### Error Messages

Missing canonical file:

- `missing runtime events file: <path>`

Missing required columns:

- `runtime events file missing columns [detail,...]: <path>`

These errors should make it obvious whether the problem is artifact production or artifact selection.

## Testing

Update `tests/test_reconcile_jforex_outcomes.py` to cover:

1. Canonical JForex runtime-events file is used even when local surrogate runtime-events file also exists.
2. Malformed local surrogate runtime-events file does not affect JForex outcome parity loading.
3. Missing canonical JForex runtime-events file fails with the expected error.
4. Malformed canonical JForex runtime-events file fails with the expected missing-columns error.

## Verification

Minimum verification:

```bash
uv run pytest -q tests/test_reconcile_jforex_outcomes.py
```

End-to-end verification after implementation:

```bash
make full-stage14-cert \
  LOCK_DIR=configs/research/governance/oco_history_dukascopy_candidate/2026-02 \
  EVAL_START=2026-02-07T00:00:00Z \
  EVAL_END=2026-02-09T00:00:00Z
```

If that passes, rerun the full monthly gate:

```bash
API_PORT=8010 METRICS_PORT_BASE=9480 uv run python scripts/run_monthly_recert.py --model-month 2026-02
```

## Risks

The main risk is exposing a real artifact-production issue that was previously masked by wildcard selection. That is acceptable and desirable for a definitive certification gate.

## Success Criteria

- Stage 14 no longer depends on wildcard runtime-event discovery.
- Local surrogate runtime-event files cannot interfere with JForex outcome parity.
- Missing or malformed canonical JForex runtime-events artifacts fail loudly and precisely.
- The failing `KeyError: 'detail'` path is replaced by deterministic artifact selection and explicit validation.

# Stage 14 Execution Lifecycle Gate Design

## Goal

Replace the stale `oco_lifecycle_pass` gate in Stage 14 with `execution_lifecycle_pass` — a gate that verifies the Java executor faithfully carried out barrier manager actions (OPEN_MARKET, CLOSE_MARKET) without failures.

## Context

The bar-level barrier manager (PR #17) moved all barrier lifecycle logic (scan → touch → hold → complete/expire) to Python. The Java side is now a thin action executor. The old `oco_lifecycle_pass` gate checked OCO-specific invariants (paired stop-limit legs, sibling cancellation, no double-live-leg drift) that no longer exist. The gate currently passes vacuously.

Barrier *logic* correctness is a Python concern, already covered by the parity test in `test_barrier_manager.py`. Stage 14 should verify that the Java side faithfully executes whatever actions Python sends.

## Design

### New gate: `execution_lifecycle_pass`

The gate passes when all three conditions hold:

1. Zero `market_order_submit_failure` operational events
2. Zero `barrier_close_failure` operational events
3. At least one `market_order_submitted` or `barrier_close_submitted` operational event (non-vacuous)

These events are already emitted by `BehemothStrategyCore.executeActions()` via `markOperationalStep()`.

### Stage14ArtifactWriter changes

**`writeLifecycleSummary()`**: Remove `Collection<OcoGroupState> groups` parameter. Instead of counting `lifecycleViolation` flags on OcoGroupState, scan `operational` category events for action execution outcomes.

**`writeReports()`**: Signature changes from `writeReports(Collection<String>, Collection<OcoGroupState>)` to `writeReports(Collection<String>)`.

**Dead code removal**:
- `recordSiblingCancelAttempt()` — never called after barrier manager rewrite
- `recordSiblingCancelFailure()` — never called
- `recordTradeTouchSync()` — never called
- `recordLifecycleViolation()` — never called
- `OcoGroupState` import removed

**CSV output**: `*_oco_lifecycle_summary.csv` → `*_execution_lifecycle_summary.csv`. Column: `oco_lifecycle_pass` → `execution_lifecycle_pass`.

### BehemothStrategyCore caller update

`stop()` calls `artifactWriter.writeReports(symbolStates.keySet(), stateStore.groups())`. Update to `artifactWriter.writeReports(symbolStates.keySet())`.

### Validation script changes

`validate_stage14_jforex_runtime_certification.py`:
- `check_id`: `oco_lifecycle_pass` → `execution_lifecycle_pass`
- `candidate_columns`: updated to match new CSV column
- Report text: remove OCO mechanics references

### Strategy bible doc

`stage_14_jforex_runtime_certification.md`:
- Replace OCO contract language (lines 52-55) with barrier manager action execution fidelity language
- Rename hard gate from `oco_lifecycle_pass` to `execution_lifecycle_pass`
- Update failure interpretation (line 76)

### Test updates

**`Stage14ArtifactWriterTest.java`**: Remove `OcoGroupState` construction, call `writeReports(symbols)` without groups, verify new CSV filename and column name.

**`test_validate_stage14_jforex_runtime_certification.py`**: Update `oco_lifecycle_pass` references to `execution_lifecycle_pass`.

### Stage 13

No changes needed — Stage 13 validates source data parity, not execution mechanics.

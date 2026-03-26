# JForex Executable Selection Parity Design

Date: 2026-03-26
Status: Proposed
Owner: Codex

## Problem

`make monthly-recert MODEL_MONTH=2026-02` now completes the six-symbol Dukascopy tester matrix and correctly carries `USDCAD` as a non-deployable `no_gate_states` month. The remaining failure is Stage 14 outcome parity for the five deployable symbols:

- JForex `predict_cycle` events report nonzero `selected_count`
- JForex `order_submitted` remains zero in the certification window
- Python locked backtest parity expects executable selections, not pre-gate candidates

This means the JForex-side notion of "selected" is currently broader than the Python backtest contract that Stage 14 is meant to certify.

## Goal

Make JForex historical certification report and compare the same executable selection semantics as successful Python backtesting.

Specifically:

- `predict_cycle.selected_count` must mean executable selections, not pre-gate model candidates
- order submission must consume the same executable set reported to parity
- pre-gate candidates and runtime-blocked candidates must remain observable as diagnostics
- Stage 14 parity must fail only on real executable-selection mismatches, not inflated pre-gate counts

## Non-Goals

- Do not relax Python backtest or governance locking semantics
- Do not introduce a special historical-only execution mode that bypasses runtime gating
- Do not redefine `order_submitted`
- Do not change the non-deployable historical-month contract added for `no_gate_states`

## Current Failure Shape

Today the JForex flow effectively mixes three different concepts:

1. candidates returned from Python inference
2. candidates still nominally selected before JForex/runtime submission gating
3. candidates actually eligible to submit orders

Stage 14 currently consumes `selected_count` from `predict_cycle`, but that count appears to be populated before the final runtime execution gate. As a result, parity compares Python executable selections against a larger JForex pre-gate pool.

## Recommended Approach

Adopt a single authoritative executable-selection set inside the JForex core.

The JForex strategy path should explicitly compute:

1. `predicted_candidates`
2. `executable_candidates`
3. `blocked_candidates`

Then:

- `predict_cycle.selected_count` is derived only from `executable_candidates`
- actual order submission uses only `executable_candidates`
- diagnostic reporting records blocked candidates separately, including blocked reasons where available

This preserves live/runtime realism while restoring a truthful parity contract.

## Design

### 1. Core Selection Contract

In [BehemothStrategyCore.java](/Users/danielfisher/repositories/behemoth/.worktrees/candidate-artifact-sync-2026-03-25/src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java), the prediction-to-submission path should be refactored so the final runtime gate is explicit and shared.

Required internal sets:

- `predicted_candidates`: candidates returned from Python
- `executable_candidates`: subset that survives all JForex/runtime submission gating and matches Python executable-selection semantics
- `blocked_candidates`: subset rejected by runtime gating, tagged with a reason

The trading core must stop using any pre-gate count as the reported selected count for parity.

### 2. Reporting Contract

In [Stage14ArtifactWriter.java](/Users/danielfisher/repositories/behemoth/.worktrees/candidate-artifact-sync-2026-03-25/src/jforex/src/main/java/com/behemoth/jforex/reporting/Stage14ArtifactWriter.java), `predict_cycle.detail` should continue to include `selected_count`, but that field now means executable selections only.

Additional diagnostics should be added alongside it, for example:

- `prediction_count=<all Python-returned candidates>`
- `selected_count=<executable candidates>`
- `blocked_count=<runtime-blocked candidates>`
- `blocked_reasons=[reason_a,reason_b,...]` or an equivalent compact encoding

This keeps existing parity consumers working while exposing why executable count may be lower than raw prediction count.

### 3. Submission Contract

Order submission must consume exactly the same `executable_candidates` set that drives `selected_count`.

If zero candidates are executable:

- `selected_count=0`
- no orders are submitted
- a blocked diagnostic is recorded if the cause is runtime gating rather than zero predictions

This ensures Stage 14 cannot observe `selected_count > 0` with `order_submitted = 0` unless there is a genuine downstream adapter/execution bug after executable selection has already been determined.

### 4. Historical Certification Behavior

Historical tester certification should remain live-faithful. It should not bypass runtime gating by reading locked predictions as direct submit instructions.

The contract is:

- Python historical locks define the authoritative executable-selection target
- JForex historical replay must independently arrive at the same executable selection semantics
- differences remain certification failures

This keeps Stage 14 meaningful for live trading rather than turning it into a broker-only transport check.

## Failure Handling

If runtime gating blocks every predicted candidate, that must be represented explicitly rather than implicitly inflating parity counts.

Expected behavior:

- `selected_count=0`
- `blocked_count>0` if predictions existed but were gated out
- `order_submitted=0`
- Stage 14 parity may still fail, but it fails for a real executable-selection mismatch

If no candidates are predicted at all:

- `prediction_count=0`
- `selected_count=0`
- `blocked_count=0`

## Test Plan

### Java core tests

Extend [BehemothStrategyCoreTest.java](/Users/danielfisher/repositories/behemoth/.worktrees/candidate-artifact-sync-2026-03-25/src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java) with cases that prove:

- raw predictions exist but runtime gating blocks all of them
- `selected_count` becomes `0`
- no orders are submitted
- blocked diagnostics carry the expected reason

### Reporting tests

Add or extend tests around [Stage14ArtifactWriter.java](/Users/danielfisher/repositories/behemoth/.worktrees/candidate-artifact-sync-2026-03-25/src/jforex/src/main/java/com/behemoth/jforex/reporting/Stage14ArtifactWriter.java) so:

- `predict_cycle.detail` includes executable `selected_count`
- `prediction_count` and `blocked_count` are emitted
- the encoded detail remains parseable by existing downstream consumers

### Python parity tests

Extend [test_reconcile_jforex_outcomes.py](/Users/danielfisher/repositories/behemoth/.worktrees/candidate-artifact-sync-2026-03-25/tests/test_reconcile_jforex_outcomes.py) so the updated `predict_cycle.detail` format still parses `selected_count` correctly and ignores the additional diagnostic fields.

### End-to-end verification

Run:

- targeted Java tests for the core/reporting path
- targeted Python tests for outcome reconciliation
- `make monthly-recert MODEL_MONTH=2026-02`

Success criteria:

- `USDCAD` remains `NO_GO` with `no_gate_states`
- deployable symbols no longer show inflated `jforex_selected_total` when no executable orders exist
- any remaining Stage 14 failures point to real executable-selection or execution mismatches

## Risks

- If the current execution gate is spread across multiple methods, the refactor may surface hidden assumptions about "selected" versus "submittable"
- Existing consumers may implicitly rely on the old pre-gate `selected_count` semantics
- Blocked-reason encoding can become noisy if it is not kept compact and stable

## Decision

Implement approach 2: align the JForex selection pipeline at the executable decision boundary, and make reporting/parity consume that single authoritative executable-selection set.

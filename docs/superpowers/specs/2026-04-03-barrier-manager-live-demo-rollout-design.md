# Barrier Manager Live-Demo Rollout Design

## Scope

Roll out the Python-owned bar-level barrier manager to the live demo stack as the sole execution authority for the active symbol universe:

- `EURUSD`
- `GBPUSD`
- `USDJPY`
- `USDCHF`
- `AUDUSD`
- `USDCAD`

This spec does not introduce a parallel shadow execution engine. It assumes the barrier-manager architecture already exists on `feat/bar-level-barrier-manager` and defines how to activate it in demo trading with enough runtime evidence to validate behavior from live runs.

## Goal

Move lifecycle ownership from Java/JForex to Python in demo trading so that:

- Python decides when a candidate begins scanning.
- Python decides whether a completed bar touched the upper or lower barrier.
- Python decides whether a touched scan becomes a live position and when that position should close.
- Java executes `OPEN_MARKET` and `CLOSE_MARKET` actions and reports broker outcomes back to Python.
- Live-demo runs produce enough artifacts to reconstruct every decision and execution event after the fact.

## Non-Goals

- Maintaining a second live OCO execution path for comparison.
- Re-implementing barrier logic in Java.
- Expanding the symbol universe beyond the active six-symbol registry.
- Solving broader production rollout questions beyond demo readiness.

## Approaches Considered

### Recommended: Single-path live-demo rollout with post-run artifact validation

Python is the only lifecycle authority. Java executes actions and emits operational telemetry. Validation comes from persisted runtime artifacts, not from a second execution engine.

Why this is the right approach:

- It exercises the target architecture directly.
- It avoids carrying old OCO lifecycle logic forward just for rollout comfort.
- It produces real demo-trading evidence quickly.
- It keeps failure analysis tractable because only one decision engine is active.

### Rejected: Dual-run shadow lifecycle

Running a second lifecycle evaluator in parallel would add complexity, timing ambiguity, and reconciliation noise. It is not justified for demo rollout when the objective is to validate the new architecture itself.

### Rejected: Symbol-phased rollout

A phased symbol rollout limits surface area but does not materially improve learning for a demo environment where blast radius is acceptable. It would only slow accumulation of execution evidence.

## Architecture

### Runtime ownership

Python owns:

- scan registration
- barrier evaluation on completed bars
- lifecycle state transitions
- close timing
- scan-to-position identity mapping

Java owns:

- calling `/predict` on each completed bar
- executing action payloads at the broker
- reporting fills, closes, and execution failures back to Python
- writing Stage 14 execution-lifecycle artifacts

No lifecycle decision is derived independently in Java.

### Request flow

On each completed bar:

1. Java calls `POST /predict`.
2. Python evaluates existing scans for the symbol against the completed bar.
3. Python emits zero or more `OPEN_MARKET` or `CLOSE_MARKET` actions.
4. Python scores current-bar candidates and registers new scans for rows where `selected_exec=1` passes all gates.
5. Java executes returned actions in order and reports broker outcomes back through the existing trade endpoints.

This ordering is required so that a bar can advance or terminate existing scans before the same request cycle admits new scans.

## State Contract

### Barrier scan ledger

The barrier-manager state must be persisted in DuckDB alongside the existing runtime tables. The ledger is first-class runtime state, not an in-memory cache.

Each scan row must capture:

- `scan_id`
- `symbol`
- `candidate_uid`
- signal bar ordinal and close timestamp
- reference price used to compute barriers
- `upper_barrier`
- `lower_barrier`
- `barrier_pips`
- `horizon`
- current lifecycle state
- scan bars remaining
- hold bars remaining
- chosen side, if touched
- touch step, if touched
- `broker_pos_id`, if opened
- `reservation_id`, if risk reservation exists
- threshold and model traceability fields
- terminal reason for `EXPIRED`, `COMPLETED`, or execution failure
- run correlation metadata

### Lifecycle states

The minimum lifecycle is:

- `SCANNING`
- `HOLDING`
- `COMPLETED`
- `EXPIRED`

An execution failure does not get to hide behind one of the normal terminal states. It must be represented either as a dedicated terminal state or as a normal state transition plus a machine-readable terminal reason that clearly marks the scan as non-recoverable.

### Identity mapping

The following invariants must hold:

- Every `OPEN_MARKET` action includes `scan_id`, `candidate_uid`, `symbol`, and side.
- Every successful fill is linked back to exactly one scan.
- Every `CLOSE_MARKET` action references a previously linked broker position.
- Java never infers position identity by parsing labels alone when explicit IDs are available from the action and fill workflow.

## API Contract

### Predict response

`POST /predict` returns a wrapper object:

```json
{
  "predictions": [],
  "actions": []
}
```

`predictions` remains the audit and observability stream for scored candidates. `actions` is the only execution instruction stream consumed by Java.

### Action semantics

`OPEN_MARKET` means:

- the completed bar caused a `SCANNING` scan to touch a barrier
- Python has already resolved direction using bar `high`, `low`, and `hl_first`
- Java should submit a single market order in the instructed direction

`CLOSE_MARKET` means:

- a holding scan has reached its completion rule in Python
- Java should close the linked broker position

Java must not reinterpret action intent, add its own lifecycle rules, or reopen missing state from legacy OCO assumptions.

## Observability And Evidence

This rollout relies on reconstruction rather than redundancy. Every demo run must leave a complete evidence trail that allows an operator to answer:

- which scans were registered
- which completed bars caused touches
- which side was chosen and why
- which actions were emitted
- which actions were submitted successfully
- which fills and closes were acknowledged by the broker
- which scans expired or failed without opening

### Required artifact streams

At minimum, persist:

- per-bar `/predict` response archives or equivalent structured logs
- barrier-scan lifecycle transition records
- action submission records
- fill-to-scan correlation records
- close submission and broker close acknowledgement records
- run-level execution summary artifacts for Stage 14 reporting

Artifacts must be keyed so they can be joined by `run_id`, `symbol`, `candidate_uid`, `scan_id`, and `broker_pos_id` where applicable.

## Failure Handling

The rollout must prefer explicit failure recording over silent retry behavior.

### Predict failure

If Python is unavailable or returns an invalid response:

- Java records a hard operational event for that bar cycle.
- No new execution action is inferred locally.
- Existing open positions remain manageable through close handling if Python later recovers.

### Open submission failure

If an `OPEN_MARKET` action cannot be submitted:

- the failure is recorded as an execution-lifecycle event
- the owning scan is marked terminal or otherwise non-recoverable with a clear reason
- the system does not leave the scan ambiguously active

### Fill correlation anomaly

If a fill arrives without a known pending action or without a resolvable scan link:

- the anomaly is surfaced in runtime artifacts
- the event contributes to Stage 14 execution-lifecycle failure reporting

### Close anomaly

If `CLOSE_MARKET` references a missing or already-closed broker position:

- record the anomaly explicitly
- surface it in certification outputs
- do not silently ignore it as expected noise

### Kill switch

Provide a single hard kill switch that:

- stops new order submissions
- keeps telemetry active
- allows close handling and reporting to continue

The rollout is not ready until that switch is verified in demo conditions.

## Go-Live Readiness

The live-demo activation is ready when all of the following are true:

1. `POST /predict` serves the wrapped `predictions + actions` contract expected by Java.
2. Barrier scan state persists through DuckDB and survives runtime restarts as required by the demo session model.
3. JForex demo runtime can submit market opens and closes from action payloads end-to-end.
4. Stage 14 certification artifacts have been updated from OCO lifecycle language to execution-lifecycle language.
5. Runtime artifact locations are deterministic and documented for operator review.
6. Kill switch behavior has been exercised successfully.

## Validation Strategy

Validation comes from live-demo evidence plus targeted pre-go-live verification.

### Before activation

Run:

- targeted Python tests covering barrier manager and response schemas
- targeted Java tests covering predict payload parsing and action execution
- Stage 14 validation tests for execution-lifecycle outputs
- a local or replay-driven demo path that proves Java can consume `actions` and report lifecycle events correctly

### During demo operation

Review:

- action counts by symbol
- open-to-fill linkage completeness
- close-to-position linkage completeness
- execution failures and anomalies
- Stage 14 execution-lifecycle summary outputs

### After demo runs

Use persisted artifacts to reconstruct:

- signal registration
- touch timing
- chosen side
- hold duration
- close reason
- any divergence between intended lifecycle and observed broker events

## Rollback

Rollback is operational, not conceptual:

- disable the barrier-manager live-demo path
- return to the last known working demo execution branch if needed

The rollback plan must not depend on repairing corrupted runtime state in place. Runtime artifacts should remain available for postmortem review regardless of rollback.

## Open Implementation Boundaries

The implementation plan derived from this spec should stay focused on:

- wiring the branch’s barrier-manager path into the demo runtime
- ensuring runtime persistence and artifact capture are complete
- updating operator and Stage 14 outputs to reflect execution lifecycle

It should not expand into unrelated strategy changes, new risk models, or broader production infrastructure work.

# Barrier Manager Recurring Demo Certification Design

## Scope

Upgrade the existing recurring JForex runtime certification flow so that it reflects the Python-owned bar-level barrier manager rather than the legacy OCO stop-limit lifecycle.

This spec updates the existing authority surfaces in place:

- `docs/strategy_bible/stage_14_jforex_runtime_certification.md`
- `docs/strategy_bible/operator_runbook.md`

It does not introduce a separate certification track. Stage 14 remains the single recurring certification authority, and the operator runbook remains the operational procedure for each demo session.

## Goal

Define an intuitive and robust recurring certification flow for every future demo session such that:

- Stage 14 remains the canonical authority for JForex runtime certification.
- tester/parity prerequisites remain explicit and distinct from live demo-session evidence
- the operator has a deterministic per-session procedure to run and review
- each demo session produces a session-scoped barrier-manager evidence bundle
- each demo session can be classified consistently as `pass`, `conditional fail`, or `fail`

## Non-Goals

- creating a new standalone certification document outside Stage 14 and the operator runbook
- redesigning Stage 13 or the broader governance ladder
- adding a parallel shadow execution engine or second certification path
- changing barrier-manager runtime behavior in this spec

## Approaches Considered

### Recommended: Extend Stage 14 and the operator runbook in place

Keep Stage 14 as the single certification authority and expand the operator runbook to define the recurring demo-session procedure and evidence review.

Why this is the right approach:

- it preserves the current governance entry points
- it avoids process sprawl and document duplication
- it keeps recurring barrier-manager demo certification where operators already look
- it separates certification authority from operational procedure without creating a second top-level process

### Rejected: Create a separate recurring demo-certification document

This would make the process more fragmented. Operators would have to reconcile Stage 14, the operator runbook, and a third authority document for the same recurring session question.

### Rejected: Move all recurring certification detail into the operator runbook

This would keep the procedure visible but would weaken Stage 14 as the canonical statement of what the runtime must prove. Certification criteria should remain in Stage 14, with the runbook explaining how to execute and review them.

## Design

### 1. Stage 14 remains the single certification authority

Stage 14 should explicitly distinguish between:

- prerequisite certification gates
- recurring demo-session certification

This preserves a clear mental model:

- prerequisite gates answer whether the JForex runtime path is fundamentally certified
- recurring demo-session certification answers whether a specific live demo session ran acceptably under the governed barrier-manager contract

Stage 14 should remain the place where both are defined, but they should not be collapsed into a single opaque requirement.

### 2. Stage 14 should use a two-layer structure

The Stage 14 page should be rewritten into two layers under one authority.

#### Prerequisite layer

This layer covers checks that establish the baseline trustworthiness of the runtime path before a session is relied upon:

- Stage 13 Dukascopy-source prerequisite
- local JForex surrogate prerequisite
- JForex tester signal parity
- JForex tester execution parity
- barrier-manager execution-lifecycle contract checks from controlled replay/tester evidence where applicable

These are not the per-session operating checks. They are the baseline gates that say the runtime path is fit to be evaluated in live demo operation.

#### Recurring session layer

This layer covers what every future demo session must prove:

- all active symbols reach acceptable readiness for the session
- the Python barrier-manager predict/action path is active
- required runtime evidence artifacts are produced and readable
- no hard lifecycle anomalies invalidate the session
- the session is classifiable from deterministic evidence rather than ad hoc operator interpretation

Stage 14 should make clear that tester parity does not substitute for session evidence, and session evidence does not erase prerequisite failures.

### 3. Operator runbook becomes the per-session execution procedure

The operator runbook should define the recurring session workflow used to satisfy the Stage 14 recurring layer.

The runbook flow should be:

1. Pre-session checks
2. Session start and readiness confirmation
3. Live observation window
4. Post-session evidence review
5. Session classification and escalation

The runbook should stay concrete and procedural. It should not restate all of Stage 14’s gate semantics, but it should show the operator exactly how to produce and review the evidence that Stage 14 expects.

### 4. The recurring flow should require a session-scoped evidence bundle

Each demo session should produce a named, session-scoped evidence bundle sufficient to reconstruct the run without relying on transient logs.

The minimum recurring evidence bundle should include:

- session-scoped predict/action archive
- barrier scan lifecycle records
- action submission records, including blocked actions where applicable
- fill and close correlation records
- runtime-events CSV used by Stage 14 validation
- symbol readiness snapshot
- Stage 14 session summary and checks outputs

The recurring certification contract should define these artifacts by purpose rather than only by informal operator knowledge. Missing or unreadable evidence should be a certification failure, not a soft warning.

### 5. Session outcomes should be deterministic

Every demo session should classify into one of three outcomes:

#### `pass`

Use when:

- all required evidence exists and is readable
- active symbols satisfy the readiness contract for the session
- predict-path activity is present and healthy
- no hard execution-lifecycle anomalies occurred
- no blocked or failed actions violate the recurring session contract

#### `conditional fail`

Use when:

- the evidence bundle exists and is usable
- the session remains diagnostically valuable
- the run shows degradations or anomalies that require investigation before it can count as a clean certified session

Examples include transient staleness, partial symbol degradation, or suspicious but non-fatal runtime behavior.

#### `fail`

Use when:

- required evidence is missing, unreadable, or malformed
- one or more symbols never reach required operational readiness
- the predict/action path is broken
- hard execution-lifecycle anomalies occur
- unresolved execution failures invalidate trust in the session outcome

The runbook and Stage 14 should use the same terms and the same definitions.

### 6. No-touch sessions should be handled explicitly

A demo session with no barrier touches should not automatically fail.

The certification rule should be:

- a no-touch session may still pass if the runtime path was live, readiness was healthy, predict-path activity was present, and the full evidence bundle was produced correctly

This matters because the recurring session gate is operational. It is meant to prove that the live demo stack ran correctly under governed conditions, not to require a trade every time the market is quiet.

### 7. Legacy OCO language should be removed from recurring certification

The Stage 14 page and operator runbook should remove or replace the remaining OCO-era semantics where they conflict with the barrier-manager architecture.

That includes:

- old OCO lifecycle terminology
- references to paired stop-limit sibling behavior as the live contract
- old lifecycle summary names such as `*_jforex_oco_lifecycle_summary.csv`
- gate names such as `oco_lifecycle_pass` where the runtime now certifies execution lifecycle rather than native OCO handling

The updated recurring flow should speak in barrier-manager terms:

- predict/action path
- barrier scan lifecycle
- execution lifecycle
- runtime evidence bundle
- session classification

### 8. Error handling should map cleanly to operator action

The operator runbook should not stop at classification. It should define what operators do next.

The recurring session procedure should map common findings into actions such as:

- immediate escalation and session failure for missing or malformed runtime evidence
- immediate escalation for hard lifecycle anomalies or unresolved close failures
- monitored follow-up for transient readiness degradation that did not invalidate the evidence bundle
- explicit note that blocked actions under an intentional kill-switch posture should be interpreted differently from unexpected blocked orders

This keeps the flow practical and avoids forcing operators to infer next steps from raw artifacts.

## Testing And Validation Expectations

This spec is documentation- and process-focused. Implementation should verify:

- Stage 14 documentation reflects the new two-layer authority structure
- the operator runbook defines the recurring demo-session flow explicitly
- terminology is internally consistent across both documents
- the recurring evidence contract aligns with the already-implemented barrier-manager runtime artifacts and Stage 14 validation semantics
- any linked reports or generated references updated by these docs still build cleanly

## Success Criteria

This work is successful when:

- an operator can read Stage 14 and understand both the prerequisite gates and the recurring session gate
- an operator can read the runbook and execute a demo-session certification without guessing at required evidence
- Stage 14 no longer reads as a legacy OCO certification page where that conflicts with the barrier-manager runtime
- recurring demo sessions can be evaluated consistently using a deterministic evidence bundle and explicit `pass` / `conditional fail` / `fail` definitions

## Risks

- If Stage 14 and the runbook drift in terminology, operators will misclassify sessions.
- If the docs are too abstract, operators will still fall back to ad hoc judgment.
- If the docs overfit to one session pattern, future valid no-touch sessions may be misread as failures.

## Implementation Notes

The implementation should prefer narrow in-place edits over broad doc churn.

Primary targets:

- `docs/strategy_bible/stage_14_jforex_runtime_certification.md`
- `docs/strategy_bible/operator_runbook.md`

Secondary linked/generated updates should be made only where required for consistency with the revised Stage 14 and runbook language.

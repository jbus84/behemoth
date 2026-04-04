# Demo Shakedown Prep Design

## Baseline Contract

- target branch: `feat/bar-level-barrier-manager`
- target commit: `b405af4`
- authoritative semantics:
  - `execution_lifecycle_pass`
  - `*_jforex_execution_lifecycle_summary.csv`
  - recurring Stage 14 demo-session certification on barrier-manager runtime semantics
- required compatibility checks:
  - confirm Stage 14 and runbook surfaces use execution-lifecycle vocabulary
  - confirm the prep work reuses existing Stage 14 validation and live-runner entry points where possible
  - confirm no part of the prep package claims live certification before a real demo session occurs

## Scope

Prepare a Monday-ready supervised shakedown package for the first real barrier-manager demo-session certification run.

This project does not execute the live demo session. It prepares the operator flow, evidence review order, existing-logic audit, and any narrow supporting updates needed so the first session can produce a complete evidence bundle and expose the remaining gaps cleanly.

The work should happen in the existing authority surfaces where possible:

- `docs/strategy_bible/stage_14_jforex_runtime_certification.md`
- `docs/strategy_bible/operator_runbook.md`
- existing Stage 14 validator/report and live-runner command surfaces

## Goal

By Monday, an operator should be able to run a supervised shakedown of the barrier-manager demo path using existing commands and existing evidence surfaces, then finish with:

- a complete and reviewable evidence bundle
- a deterministic post-session review flow
- a clear classification of the session as a shakedown, not yet a finalized recurring certified session
- a bounded record of the gaps exposed by the run

## Non-Goals

- executing a real live demo session in this task
- inventing synthetic demo evidence
- creating a parallel certification system
- replacing existing Stage 14 validation/reporting with a new standalone toolchain
- broad automation work that is not required for Monday’s shakedown

## Existing Logic Audit

The implementation should audit and reuse the current repo logic before adding anything new.

Primary existing surfaces to inspect and reuse:

- `make jforex-live`
- `make demo-cert-monitor`
- `make stage14-jforex-cert`
- `scripts/validate_stage14_jforex_runtime_certification.py`
- `docs/analysis/stage14_jforex_runtime_certification_report.md`
- `docs/strategy_bible/generated/stage_14_snapshot.md`
- runtime artifact outputs under `data/analysis/backtest_reconcile/`
- readiness and runtime-event artifacts already emitted by the barrier-manager rollout

The design assumes the default path is:

1. reuse current commands and reports
2. tighten documentation around those existing surfaces
3. add a narrow helper only if the audit shows the operator would otherwise need to infer missing steps or manually stitch evidence in an error-prone way

## Approaches Considered

### Recommended: Monday-ready shakedown package using existing logic

Prepare the supervised shakedown around the current runtime, validator, and report surfaces, then add only the minimum supporting changes required to make Monday’s session operationally clear.

Why this is the right approach:

- it matches the real constraint that no live data is available until Monday
- it exercises the actual barrier-manager certification flow rather than a synthetic substitute
- it keeps process sprawl under control
- it leaves a clean gap list for the post-shakedown hardening pass

### Rejected: Docs-only cleanup before Monday

This would improve wording, but it would still leave too much risk that the operator flow is incomplete or that artifact discovery is awkward in practice.

### Rejected: New shakedown-specific certification stack

This would overfit a one-off rehearsal and duplicate logic that already exists in Stage 14 and the barrier-manager runtime evidence path.

## Design

### 1. Treat Monday as a supervised shakedown, not as immediate recurring certification

The package should explicitly distinguish:

- the supervised shakedown run
- the recurring demo-session certification process it is rehearsing

The shakedown is successful if it produces a complete evidence bundle and exposes the remaining process/tooling gaps. It does not need to prove that no further documentation or operator refinements are needed afterward.

Stage 14 and the operator runbook should therefore describe Monday as:

- operationally real
- evidence-bearing
- suitable for post-session review
- not yet the final steady-state recurring certification model until the exposed gaps are incorporated

### 2. Keep the work inside the current Stage 14 and operator surfaces

The main deliverables should be updates to the existing authority and procedure documents, not a separate long-lived shakedown manual.

`stage_14_jforex_runtime_certification.md` should:

- remove the remaining operator-relevant placeholders
- explain how the shakedown sits relative to the prerequisite layer and the recurring session layer
- clarify which artifacts are authoritative during post-session review
- explain how a shakedown session is judged without prematurely treating it as a fully hardened recurring gate

`operator_runbook.md` should:

- define the Monday shakedown steps in execution order
- point the operator to the existing commands and artifact locations
- define the post-session review order
- provide a lightweight gap-capture structure

### 3. Organize the operator flow into five explicit phases

The package should structure the supervised shakedown into:

1. preflight
2. session launch
3. live observation
4. post-session evidence review
5. gap capture

This is important because the current recurring Stage 14 framing is strong on certification outcomes but still leaves room for operator ambiguity in the exact first-run flow.

Each phase should answer a different question:

- preflight: are we ready to run?
- launch: did the session actually start in the governed way?
- observation: did the runtime appear healthy during the session?
- review: do we have a complete evidence bundle?
- gap capture: what do we change after Monday?

### 4. Reuse current command entry points and artifact paths where possible

The operator should not need a new orchestration layer if the current repo already exposes the required entry points.

The package should prefer:

- `make demo-cert-monitor` for observation setup
- `make jforex-live` for the live runner
- `make stage14-jforex-cert` and existing report outputs for post-session review

If the audit finds that one of those is insufficient for Monday, the fix should be narrow and specific, for example:

- a missing report pointer
- an ambiguous artifact path
- a missing note about readiness versus evidence freshness
- a tiny helper for artifact discovery

It should not introduce a second certification workflow.

### 5. Define the minimum evidence bundle in operator terms

The shakedown package should tell the operator exactly what to inspect after the run and in what order.

The minimum review set should include:

- live readiness snapshot
- per-symbol JForex runtime events
- signal parity summaries
- execution parity summaries
- execution-lifecycle summaries
- operational readiness summaries
- outcome parity summary
- Stage 14 certification summary/checks
- Stage 14 report and generated snapshot

The operator should be able to answer, in order:

1. did all expected artifacts exist?
2. did they belong to the same session window?
3. do they indicate a broadly healthy barrier-manager runtime path?
4. what gaps or ambiguities did the shakedown expose?

### 6. Add an explicit shakedown gap-capture mechanism

The first real session is expected to expose issues. The package should make those visible instead of forcing them into informal memory or chat history.

The gap-capture mechanism can stay lightweight. It may simply be a small section in the runbook or a narrow template/checklist that records:

- missing artifact
- unclear operator step
- validator or report ambiguity
- runtime anomaly
- “works but too manual”

Each captured gap should include:

- observed symptom
- affected command or artifact
- whether it blocked classification or only made the review awkward
- recommended follow-up owner or surface

This is what turns Monday into a useful supervised shakedown rather than just a one-off run.

### 7. Remove operator-relevant placeholders from Stage 14

The current Stage 14 page still contains placeholders that weaken Monday-readiness:

- `Exact Calculations`
- `Causality / Leakage Controls`
- `Interpretation Guide`
- `Operator Decision Tree`
- `How To Interpret Outputs`
- `What To Do If It Fails`

The implementation should either:

- replace these with concise real guidance, or
- remove/restructure them if they do not help the operator execute the shakedown

The goal is not to make the page longer. The goal is to make the authority surface less ambiguous for Monday’s supervised run.

### 8. Keep any new logic narrow and audit-driven

If the existing logic audit reveals a genuine Monday blocker, the implementation may update existing logic, but only where necessary.

Valid reasons to change code or validation logic include:

- the evidence bundle cannot be discovered cleanly from existing outputs
- current reports omit information the operator must have for shakedown classification
- the existing validator/report wording contradicts the shakedown process

Invalid reasons include:

- creating a convenience wrapper for a process that is already clear
- speculative automation that does not remove real operator ambiguity
- building a second artifact format for the same evidence

## Testing And Validation Expectations

Implementation should verify:

- Stage 14 and operator runbook language are internally consistent with the current barrier-manager branch semantics
- the documented shakedown flow points to real commands and real artifact locations
- existing validator/report logic still builds cleanly after any narrow updates
- any added helper logic is justified by a concrete gap found during the audit
- `uv run mkdocs build` passes on the updated branch

If the implementation changes validator or report logic, the relevant tests should be updated and run as part of the work.

## Success Criteria

This work is successful when:

- an operator can follow a Monday-ready supervised shakedown procedure without inventing steps
- the procedure uses current commands and current artifact paths wherever possible
- the Stage 14 authority page no longer contains operator-relevant placeholders that would block interpretation
- the post-session review order is explicit enough to determine whether the evidence bundle is complete
- the package includes a clear way to record the remaining gaps exposed by the shakedown
- no document incorrectly claims that live recurring certification has already happened

## Risks

- If the docs are polished without auditing existing logic, Monday may still reveal avoidable process gaps.
- If the work adds too much new automation, it may create a second process instead of strengthening the current one.
- If shakedown status is not distinguished clearly from recurring certification, operators may over-claim what Monday proves.

## Implementation Notes

Primary targets:

- `docs/strategy_bible/stage_14_jforex_runtime_certification.md`
- `docs/strategy_bible/operator_runbook.md`
- existing Stage 14 validator/report logic only if the audit shows a concrete gap

The implementation should stay disciplined:

- audit existing logic first
- reuse existing logic where possible
- update existing logic only where the operator flow would otherwise be ambiguous or error-prone
- prepare Monday’s supervised shakedown without pretending the live run has already occurred

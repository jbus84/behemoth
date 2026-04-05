# Stage 14 Execution Lifecycle Port To Main Design

## Baseline Contract

- target branch: `main`
- target commit: `6dc7de5`
- authoritative semantics:
  - `execution_lifecycle_pass`
  - `*_jforex_execution_lifecycle_summary.csv`
  - Stage 14 certification chain on `main` must match barrier-manager execution-lifecycle semantics end to end
- required compatibility checks:
  - confirm the Stage 14 certification chain on `main` no longer consumes or emits `oco_lifecycle_pass`
  - confirm the Stage 14 certification chain on `main` no longer points at `*_jforex_oco_lifecycle_summary.csv`
  - confirm the remaining `oco_lifecycle` references, if any, are outside the scoped Stage 14 certification chain

## Scope

Port the remaining Stage 14 certification chain on `main` from OCO lifecycle naming to execution-lifecycle naming so `main` becomes internally consistent with the barrier-manager runtime already merged there.

This is a targeted integration fix. It is not a broad merge of the entire feature branch, and it is not a repo-wide legacy naming sweep.

The scope includes all files that participate in the Stage 14 certification chain on `main`:

- lifecycle artifact producers
- lifecycle artifact consumers
- lifecycle tests
- Stage 14 authority/generated docs
- local-surrogate lifecycle surfaces only where they directly feed the same certification chain

## Goal

Make `main` use execution-lifecycle semantics end to end for Stage 14 so a PR into `main` can carry the Monday shakedown-prep work without branch-truth mismatch.

After this fix:

- JForex lifecycle artifacts should be produced as execution-lifecycle summaries
- Stage 14 validators and Make targets should consume execution-lifecycle summaries
- Stage 14 tests should assert execution-lifecycle names
- Stage 14 authority/generated docs on `main` should describe the same certification contract the code actually implements

## Non-Goals

- merging the entire `feat/bar-level-barrier-manager` branch into `main`
- rewriting unrelated legacy OCO references elsewhere in the repo
- changing barrier-manager runtime behavior
- redesigning the Stage 14 process beyond what is required to make the certification chain internally consistent

## Problem

`main` is currently in a split state:

- the core barrier-manager runtime line is already present
- but parts of the Stage 14 certification chain on `main` still use OCO lifecycle naming

This creates an inconsistent system:

- runtime semantics imply execution lifecycle
- certification semantics still partly imply OCO lifecycle

That inconsistency blocks a clean PR into `main` because the Monday shakedown-prep work assumes the Stage 14 chain already uses execution-lifecycle semantics.

## Approaches Considered

### Recommended: Minimal one-pass Stage 14 port on `main`

Update only the files that produce, consume, test, or document the Stage 14 certification chain on `main`.

Why this is the right approach:

- it fixes the actual blocker rather than patching around it
- it avoids replaying unrelated feature-branch history
- it keeps the conflict surface small
- it produces a clean and coherent `main` certification path

### Rejected: Merge the larger feature branch line again

Most of the runtime line is already on `main`. Re-merging the larger branch introduces conflict noise without improving the precision of the fix.

### Rejected: Docs-only patch

If the producer, consumer, and test surfaces still say OCO lifecycle while docs say execution lifecycle, `main` remains broken in a more subtle way.

## Design

### 1. Update the lifecycle artifact producers

The JForex Stage 14 artifact writer on `main` must emit execution-lifecycle artifacts instead of OCO lifecycle artifacts.

That means:

- CSV header field should become `execution_lifecycle_pass`
- lifecycle artifact path should become `*_jforex_execution_lifecycle_summary.csv`
- supporting tests should assert the new header and filename

This is the start of the chain. If the producer remains on OCO naming, every downstream consumer must either stay wrong or carry translation logic that should not exist anymore.

### 2. Update the lifecycle artifact consumers

The Python validator and Make targets must consume the same execution-lifecycle artifact names and columns the Java writer now produces.

That means:

- `Makefile` Stage 14 lifecycle glob should point to `*_jforex_execution_lifecycle_summary.csv`
- the Stage 14 validator should use `execution_lifecycle_pass` as the lifecycle check id and preferred candidate column
- the checked-in Stage 14 report/snapshot generated from that validator should reflect the same names

The same principle applies to the local-surrogate side only where it directly feeds the Stage 14 certification path on `main`. The implementation must verify that boundary explicitly. If `local-jforex-cert`, its validator, or its generated outputs still feed the same lifecycle naming chain, they are in scope for this one-pass port. If they do not, they should stay out of scope.

### 3. Update the certification-chain tests

The tests that enforce the Stage 14 chain on `main` must switch with the code, not after it.

This includes:

- Python validator tests expecting lifecycle column names
- Java `Stage14ArtifactWriterTest`
- any test fixtures or helper rows that still write `oco_lifecycle_pass`

The goal is that the Stage 14 chain has one naming regime after this fix. Tests should make it hard to regress back into the mixed state.

### 4. Update the Stage 14 authority page and generated outputs

The checked-in Stage 14 authority page on `main` should reflect the execution-lifecycle semantics that the certification chain now uses.

This includes:

- Stage 14 input names
- lifecycle pass flag names
- summary filenames

The generated report and generated snapshot should then be regenerated from the updated validator so the committed outputs match the implemented chain rather than preserving stale OCO-era headers.

### 5. Keep the boundary strict

This fix should touch only files that are part of the Stage 14 certification chain on `main`.

In-scope examples:

- `Makefile`
- `scripts/validate_stage14_jforex_runtime_certification.py`
- `tests/test_validate_stage14_jforex_runtime_certification.py`
- `src/jforex/src/main/java/com/behemoth/jforex/reporting/Stage14ArtifactWriter.java`
- `src/jforex/src/test/java/com/behemoth/jforex/Stage14ArtifactWriterTest.java`
- `docs/strategy_bible/stage_14_jforex_runtime_certification.md`
- generated Stage 14 report/snapshot outputs
- local-surrogate lifecycle validator surfaces if they still directly feed this same certification path

Out-of-scope examples:

- unrelated historical docs that mention OCO lifecycle
- legacy analysis reports not used by the Stage 14 chain
- broader runtime refactors

### 6. Sequence the implementation as a single certification-chain port

The cleanest implementation order is:

1. tests that expose the naming mismatch
2. producer updates
3. consumer updates
4. docs/generated output regeneration
5. end-to-end verification on `main`

This ensures the fix stays chain-oriented rather than bouncing randomly between docs and code.

## Testing And Validation Expectations

The implementation should verify:

- Java Stage 14 artifact writer tests pass
- Python Stage 14 validator tests pass
- local-surrogate lifecycle validation tests pass if that surface is changed
- `make stage14-jforex-cert` passes on the `main`-based branch
- `uv run mkdocs build` passes

Final regression verification should include a scoped grep showing that the Stage 14 certification chain no longer contains:

- `oco_lifecycle_pass`
- `*_jforex_oco_lifecycle_summary.csv`

except for intentionally out-of-scope legacy surfaces that do not feed this chain.

## Success Criteria

This work is successful when:

- the Stage 14 certification chain on `main` produces execution-lifecycle artifacts
- the Stage 14 certification chain on `main` consumes execution-lifecycle artifacts
- the Stage 14 tests on `main` enforce execution-lifecycle naming consistently
- the checked-in Stage 14 authority/generated docs on `main` match the same execution-lifecycle contract
- the Monday shakedown-prep work can then be promoted into `main` without another branch-truth mismatch

## Risks

- If the fix only updates docs and generated files, the chain remains internally inconsistent.
- If the fix only updates the validator but not the writer, runtime outputs and certification inputs diverge.
- If the fix overreaches into unrelated legacy surfaces, it creates unnecessary review and merge risk.

## Implementation Notes

The key discipline is to treat this as one certification chain:

- produce lifecycle artifacts
- consume lifecycle artifacts
- test lifecycle artifacts
- document lifecycle artifacts

Do not let `main` stay in a mixed state after this work.

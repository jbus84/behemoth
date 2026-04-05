# Stage 14 Pre-Monday Contract Repair Design

## Baseline Contract
- Target branch: `main`
- Target commit: `9de79b3`
- Authoritative semantics:
  - Stage 14 must distinguish `certification_outcome` from `go_decision`
  - `NO_GO` is not a certification failure
  - current Stage 14 artifacts are tester/runtime outputs only, not Monday live-demo evidence
- Required compatibility checks:
  - `scripts/validate_stage14_jforex_runtime_certification.py` is the Stage 14 authority script
  - `docs/strategy_bible/stage_14_jforex_runtime_certification.md` is the Stage 14 authority page
  - `make stage14-jforex-cert` is the canonical command path

## Problem Statement
Current Stage 14 is not internally correct enough for Monday’s live-demo run. The checked-in Stage 14 report surfaces are stale relative to the repaired Stage 13 truth, and the Stage 14 contract still uses a weaker pass/fail-plus-`nogo` framing instead of the clearer two-axis model already established for Stage 12 and Stage 13.

That creates two risks:
1. Monday runtime evidence could be interpreted through stale contract semantics.
2. Stage 14 failures could mix certification truth with deployability truth, making anomalies harder to diagnose.

## Goals
Before Monday, Stage 14 should be tester-ready and internally consistent:
- emit `certification_outcome = PASS | FAIL`
- emit `go_decision = GO | NO_GO`
- preserve the rule that `NO_GO` is not itself a certification failure
- align the Stage 14 validator, summary outputs, report, snapshot, and authority doc
- regenerate current Stage 14 outputs from today’s tester/runtime artifacts so checked-in surfaces match branch truth

## Non-Goals
- Producing fresh live-demo evidence before Monday
- Redesigning the entire Stage 14 gate set
- Changing runtime adapter behavior solely to make Stage 14 green on current artifacts

## Recommended Approach
Use a focused Stage 14 contract repair rather than waiting for Monday’s live run.

Why this is the right scope:
- it separates contract correctness from live-runtime validation
- it lets Monday test the broker/runtime path, not expose known reporting drift
- it keeps changes bounded to validator, tests, docs, and generated certification surfaces

## Stage 14 Outcome Model
For each symbol, Stage 14 should emit:
- `certification_outcome = PASS | FAIL`
- `go_decision = GO | NO_GO`

Interpretation:
- `PASS / GO`: the runtime adapter certified correctly and the symbol is operationally tradeable
- `PASS / NO_GO`: the runtime adapter certified correctly, but the symbol should not proceed operationally
- `FAIL / NO_GO`: certification failed, so the symbol is not operationally trusted

`FAIL / GO` should not appear in final outputs. If certification fails, the final operational decision should resolve conservatively to `NO_GO`.

## Gate Semantics
The Stage 14 hard certification gates continue to decide `certification_outcome`. These remain broker/runtime correctness questions such as:
- Stage 13 prerequisite
- JForex signal parity
- JForex execution parity
- execution lifecycle
- operational readiness
- any other current Stage 14 hard prerequisites that remain in validator scope

`go_decision` should then be resolved from the symbol’s deployability/runtime status. Historically or operationally blocked symbols may still certify as `PASS / NO_GO` when the runtime behaves correctly and the block is expected.

This implies the validator must no longer treat `NO_GO` itself as a failed certification path.

## Required Changes
### 1. Validator and Summary Semantics
Update `scripts/validate_stage14_jforex_runtime_certification.py` so it:
- emits `certification_outcome` and `go_decision`
- preserves Stage 13 `PASS / NO_GO` semantics rather than collapsing them to failed prerequisite status
- resolves final operational decision conservatively when certification fails
- keeps gate-level check rows explicit and unchanged in spirit

### 2. Test Coverage
Update Stage 14 validator tests and any affected Java/report tests so they enforce:
- `NO_GO` does not automatically imply failed certification
- final outputs do not emit `FAIL / GO`
- regenerated summary/report/snapshot surfaces reflect the same two-axis model

### 3. Authority Doc Repair
Update `docs/strategy_bible/stage_14_jforex_runtime_certification.md` to:
- define the two-axis interpretation explicitly
- remove wording that treats `nogo` as a blocked certification path
- tighten remaining placeholder-style sections so Monday operators are reading current truth

### 4. Regenerated Outputs
Regenerate:
- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv`
- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`
- `docs/analysis/stage14_jforex_runtime_certification_report.md`
- `docs/strategy_bible/generated/stage_14_snapshot.md`

These regenerated outputs may still be red overall on current tester artifacts. That is acceptable. The requirement is that they are red or green for the correct reasons and using the correct semantics.

## Verification
Required verification before calling this ready:
- targeted Stage 14 validator tests pass
- any affected Java/report tests pass
- `make stage14-jforex-cert` succeeds on current tester/runtime artifacts
- `uv run mkdocs build` succeeds
- final generated Stage 14 outputs clearly separate `certification_outcome` from `go_decision`

## Expected Outcome
After this repair, Stage 14 will be internally correct and tester-ready before Monday.

That means:
- the contract will be aligned with the repaired Stage 13 semantics
- the docs and generated certification surfaces will match current branch truth
- Monday’s live-demo run can focus on real runtime evidence rather than surfacing known contract drift

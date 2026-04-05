# Stage 13 Dukascopy Python Gate Repair Design

## Baseline Contract

- target branch: `main`
- target commit: `dbd5ae3`
- authoritative semantics:
  - Stage 13 is the Dukascopy-source prerequisite gate for the Python decision layer
  - Stage 13 hard gates must be driven by Stage 12 prerequisite status plus Dukascopy/TestClient evidence only
  - local JForex surrogate evidence is not part of the Stage 13 certification contract
- required compatibility checks:
  - confirm Stage 13 no longer consumes `*_local_jforex_*` artifacts through broad `*_jforex_*` globs
  - confirm Stage 13 evaluates `stage12_api_parity_pass`, `dukascopy_testclient_signal_parity_pass`, and `dukascopy_testclient_execution_parity_pass` from the correct evidence families
  - confirm Stage 13 report and authority doc describe the same gate the validator implements

## Scope

Repair Stage 13 so it certifies the correct Python-driven Dukascopy gate instead of mixing local JForex surrogate artifacts into the result.

The work should:

- restore the Stage 12 prerequisite to the Stage 13 validator
- restrict Stage 13 signal and execution checks to Dukascopy/TestClient evidence only
- remove local JForex surrogate artifacts from the Stage 13 hard-gate path
- update Stage 13 docs and generated outputs so they match the repaired validator
- rerun Stage 13 to identify the real remaining failing symbols under the corrected gate

## Goal

Make Stage 13 robust and informative under the Python-managed barrier lifecycle architecture.

After this repair:

- Stage 13 will represent Dukascopy-source replay against the Python decision layer
- Stage 12 will remain an explicit prerequisite, not a substitute for Stage 13 evidence
- local JForex surrogate artifacts will no longer satisfy or fail Stage 13
- remaining red symbols will reflect real Dukascopy/TestClient issues instead of cross-layer contamination

## Non-Goals

- redesigning Stage 14
- changing Stage 13 into a JForex certification gate
- broad repo-wide renaming unrelated to the Stage 13 certification chain
- fixing every remaining Stage 13 red symbol as part of the contract repair itself

## Problem

Stage 13 has drifted away from both its documented contract and the new Python-driven architecture.

The current authority doc says Stage 13 should require:

- `stage12_api_parity_pass`
- `dukascopy_testclient_signal_parity_pass`
- `dukascopy_testclient_execution_parity_pass`

But the current validator instead checks:

- runtime artifacts completeness
- mixed `*_jforex_signal_parity_summary.csv` inputs
- mixed `*_jforex_operational_ready_summary.csv` inputs

Because the current Make target uses broad `*_jforex_*` globs, Stage 13 accidentally consumes `*_local_jforex_*` summaries. That means a local surrogate file can make a Dukascopy gate green or red, which is architecturally wrong.

The current reproduced failure on `main` illustrates the issue:

- `make stage13-dukascopy-cert` currently leaves `USDCAD` red
- the failing source is `data/analysis/backtest_reconcile/USDCAD_local_jforex_signal_parity_summary.csv`
- that file should not be part of a pure Dukascopy/Python certification gate

## Approaches Considered

### Recommended: Minimal contract repair first

Repair the validator, Make target, tests, and docs so Stage 13 measures the correct gate, then rerun the certification and inspect remaining failures.

Why this is the right approach:

- it produces a trustworthy diagnosis quickly
- it prevents wasted time debugging artifacts that do not belong in Stage 13
- it preserves the user’s intended architecture boundaries
- it keeps scope tight enough for a single implementation plan

### Rejected: Full Stage 13 redesign first

A larger redesign may be appropriate later, but it is not necessary to answer why Stage 13 is currently failing.

### Rejected: Debug `USDCAD` first under the current gate

The current gate is contaminated by local-surrogate inputs. Debugging the remaining red symbol before repairing the contract risks chasing the wrong root cause.

## Design

### 1. Restore the correct Stage 13 contract

Stage 13 should evaluate four checks:

- `stage12_api_parity_pass`
- `dukascopy_runtime_artifacts_complete_pass`
- `dukascopy_testclient_signal_parity_pass`
- `dukascopy_testclient_execution_parity_pass`

The first check is an explicit prerequisite. The remaining three are the direct Dukascopy-source certification checks.

The validator should produce a final `stage13_dukascopy_testclient_pass` only when all four are green for the symbol.

### 2. Restrict evidence families to the correct layer

Each Stage 13 check should have one clear source family:

- `stage12_api_parity_pass`
  - from the Stage 12 summary artifact
- `dukascopy_runtime_artifacts_complete_pass`
  - from Dukascopy replay runtime evidence presence/completeness
- `dukascopy_testclient_signal_parity_pass`
  - from Dukascopy/TestClient signal parity artifacts only
- `dukascopy_testclient_execution_parity_pass`
  - from Dukascopy/TestClient execution parity artifacts only

The implementation must stop using broad `*_jforex_*` globs that match both real JForex and local-surrogate files.

If explicit Dukascopy/TestClient summary filenames already exist, Stage 13 should consume them directly. If not, the validator must filter the current files by unambiguous filename pattern rather than by broad suffix alone.

### 3. Remove local surrogate evidence from Stage 13 hard gates

Local JForex surrogate artifacts may remain in the repo as diagnostics, but they must no longer participate in the Stage 13 pass/fail decision.

The corrected Stage 13 report should make this boundary obvious:

- Stage 13 is about Dukascopy-source replay against Python behavior
- local surrogate is a separate Java-side diagnostic prerequisite outside this gate

### 4. Align authority docs and generated outputs with branch truth

The authority page and generated outputs must describe the repaired Stage 13 contract exactly.

This includes:

- removing the remaining placeholders from the Stage 13 authority page where they impede interpretation
- documenting the corrected hard gates and evidence sources
- regenerating the Stage 13 report and snapshot after the validator is repaired

The resulting docs should make failure localization intuitive:

- Stage 12 red means the Python baseline is untrusted
- Stage 13 signal red means Dukascopy replay is not reproducing governed Python selection behavior
- Stage 13 execution red means Python-managed lifecycle outcomes diverge under Dukascopy replay
- runtime artifacts red means the run is uncertifiable because the evidence bundle is incomplete

### 5. Rerun Stage 13 after the contract repair

After the validator is corrected, rerun `make stage13-dukascopy-cert` and inspect the remaining red symbols.

The first concrete question after repair is:

- does `USDCAD` remain red under the actual Dukascopy/TestClient gate,
- or was the prior failure only caused by the wrongly included local-surrogate summary?

The implementation plan should treat this rerun and diagnosis as part of the work, because the user’s primary goal is to understand why Stage 13 is failing now.

## Verification

A repaired Stage 13 contract is complete only if all of the following hold:

- Stage 13 validator tests pass and explicitly prove local-surrogate files can no longer affect the Stage 13 result
- `make stage13-dukascopy-cert` completes successfully on `main`
- regenerated Stage 13 report and snapshot reflect the repaired contract
- a scoped regression grep shows the Stage 13 certification chain no longer references `*_local_jforex_*` as hard-gate inputs
- the resulting Stage 13 outputs identify the actual remaining failing symbols under the corrected gate

## Risks And Boundaries

The main risk is partial repair.

If the docs are updated but the validator still accepts local-surrogate files, the gate remains wrong. If the validator is repaired but generated outputs and tests are left behind, future regressions will be hard to detect.

The boundary should remain tight:

- fix the Stage 13 certification chain only
- do not broaden into Stage 14 or unrelated local-surrogate cleanup
- do not start symbol-level behavioral fixes until the gate itself is repaired

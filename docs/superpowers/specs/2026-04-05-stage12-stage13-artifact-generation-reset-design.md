# Stage 12 And Stage 13 Artifact Generation Reset Design

## Baseline Contract

- target branch: `stage12-dukascopy-artifact-generation-2026-04-05`
- target commit: `7f98f4b`
- authoritative semantics:
  - Stage 12 is the final Python/API-side certification gate before broker-source certification begins
  - Stage 13 is the Dukascopy/TestClient certification gate that depends on Stage 12
  - final per-symbol outputs must resolve to `certification_outcome = PASS | FAIL` and `go_decision = GO | NO_GO`
  - local JForex surrogate evidence is not part of Stage 12 or Stage 13 hard-gate evaluation
- required compatibility checks:
  - confirm the repo no longer relies on empty `stage12-api-parity` or no-op `dukascopy-testclient-parity` stubs as the authoritative generation path
  - confirm the new artifact-generation path can produce Stage 12 and Stage 13 artifacts for the full six-symbol universe by default
  - confirm final emitted outputs do not leave symbols in an `UNKNOWN` end state

## Scope

Replace the broken legacy Stage 12 and Stage 13 artifact-generation entrypoints with one new authoritative full-universe certification-generation flow.

This work should:

- generate Stage 12 per-symbol artifacts for the active six-symbol universe
- generate Stage 13 Dukascopy/TestClient replay artifacts for the active six-symbol universe
- generate the runtime-events evidence Stage 13 depends on
- enforce Stage 12 as a hard prerequisite to Stage 13 on each symbol
- emit final per-symbol outputs that distinguish certification status from operational/governance decision
- retire the dead legacy command surfaces and stale doc references that point at missing or no-op paths

## Goal

Restore a runnable end-to-end Stage 12 to Stage 13 certification pipeline.

After this reset:

- the repo will have one authoritative command path for generating Stage 12 and Stage 13 artifacts
- Stage 12 will run first and determine whether a symbol may proceed to Stage 13 generation
- Stage 13 will run only on symbols with valid Stage 12 certification inputs
- final per-symbol results will resolve to `PASS | FAIL` plus `GO | NO_GO`
- operators and docs will point at a live command path instead of dead stubs or missing scripts

## Non-Goals

- redesigning Stage 14
- rewriting unrelated research stages below Stage 12
- changing the governed reduced-core research truth itself
- introducing an `UNKNOWN` final outcome state
- keeping legacy stub entrypoints alive just for compatibility

## Problem

The Stage 12 to Stage 13 certification chain is currently broken at the artifact-generation layer.

Current branch truth:

- `make stage12-api-parity` exists but has no recipe
- `make dukascopy-testclient-parity` is a legacy no-op stub
- `scripts/replay_dukascopy_testclient.py` is referenced by docs but missing from the repo
- Stage 13 validator and docs were repaired, but all six symbols remain red because the Stage 12 summaries, Dukascopy/TestClient replay summaries, and runtime-events artifacts are missing

So the current issue is no longer a contract problem. It is an execution-path problem: the repo lacks a working authoritative way to produce the artifacts that Stage 12 and Stage 13 actually consume.

## Approaches Considered

### Recommended: One new unified artifact-generation path

Create one new authoritative orchestration path that produces Stage 12 artifacts first, then Stage 13 artifacts, and finally emits normalized per-symbol outputs for the active universe.

Why this is the right approach:

- it removes ambiguity about which command path is real
- it keeps Stage 12 and Stage 13 coupled in the correct order
- it makes the six-symbol operational workflow simple and repeatable
- it avoids preserving broken legacy surfaces that already mislead operators

### Rejected: Separate new Stage 12 and Stage 13 generators with no unified entrypoint

This would work technically, but it would make it easier for the stages to drift again and would preserve the current operator confusion about which command to run first.

### Rejected: Thin wrappers around the old names only

Keeping the dead names as the public surface would preserve ambiguity and encourage continued documentation drift. The new flow should be explicit and authoritative.

## Design

### 1. Create one authoritative orchestration command

Introduce one new top-level command path for certification artifact generation, full-universe by default.

Conceptually, the command should:

1. enumerate the active six-symbol universe
2. generate Stage 12 artifacts for each symbol
3. evaluate Stage 12 certification outcome for each symbol
4. generate Stage 13 artifacts only for symbols that passed Stage 12 generation/validation prerequisites
5. emit a normalized final summary for all symbols

This command becomes the only authoritative generation path for these stages.

The broken legacy surfaces should be removed or explicitly retired from active docs and Make targets.

### 2. Treat Stage 12 as the capstone Python-side certification phase

Stage 12 is the end of the Stage 0 through Stage 12 Python-side certification line. It asks whether the production Python/API runtime reproduces governed reduced-core truth on canonical historical replay.

So the new orchestrator should treat Stage 12 as a hard prerequisite:

- if Stage 12 cannot produce valid artifacts for a symbol, the symbol does not proceed to Stage 13 generation
- if Stage 12 generates artifacts and fails certification, the symbol does not proceed to Stage 13 generation
- only Stage 12-passing symbols are eligible for Stage 13 generation

This ordering should be explicit in both code and docs.

### 3. Keep Stage 12 and Stage 13 producers separate under one orchestrator

The implementation should keep the actual artifact producers modular:

- Stage 12 artifact producer
- Stage 13 Dukascopy/TestClient artifact producer
- shared orchestration entrypoint

That preserves clear boundaries:

- Stage 12 producer is responsible for Stage 12 parity artifacts
- Stage 13 producer is responsible for Dukascopy/TestClient replay and runtime-events artifacts
- orchestrator is responsible for symbol enumeration, sequencing, final aggregation, and resolved outcomes

If existing working logic can be reused, prefer reuse over reimplementation. `scripts/validate_api_parity.py` appears reusable for Stage 12 output production and should be evaluated first.

### 4. Emit resolved final outcomes

Final emitted outputs must not leave a symbol in an ambiguous state.

For each symbol, the orchestrator should emit:

- `certification_outcome = PASS | FAIL`
- `go_decision = GO | NO_GO`

Semantics:

- `PASS` means the symbol was evaluated correctly and the certification gates passed
- `FAIL` means the symbol could not be certified or the certification gates failed
- `GO` means the evaluated result permits operational progression
- `NO_GO` means the evaluated result says the symbol should not proceed operationally

`UNKNOWN` may exist internally while the orchestrator is still running, but it must not appear in final emitted artifacts.

### 5. Normalize the relationship between certification and governance decision

The new flow should not overload certification with operational meaning.

A symbol can be:

- `PASS + GO`
- `PASS + NO_GO`
- `FAIL + NO_GO`

The important point is that `NO_GO` is not synonymous with evaluation failure. It is the operational conclusion after valid evaluation.

This distinction should be visible in final summaries and reports so operators can answer two separate questions:

- did the certification pipeline evaluate the symbol correctly?
- should the symbol proceed?

### 6. Replace dead docs and stale references

Docs must stop pointing at missing or no-op paths.

This project should update the relevant Stage 12 and Stage 13 authority pages and any operator-facing references so they point at the new authoritative command and its real outputs.

At minimum, remove or replace:

- references to the missing `scripts/replay_dukascopy_testclient.py`
- references that imply `make stage12-api-parity` or `make dukascopy-testclient-parity` are already working if those names are retired or repurposed

The resulting docs should explain the sequence clearly:

- run the new unified command
- Stage 12 executes first
- Stage 13 executes only for Stage 12-eligible symbols
- inspect final `PASS | FAIL` and `GO | NO_GO` outputs

## Verification

This reset is complete only if all of the following hold:

- the new authoritative command runs for the full six-symbol universe by default
- Stage 12 artifacts are generated through the new flow
- Stage 13 artifacts are generated through the new flow for Stage 12-eligible symbols only
- final per-symbol outputs resolve to `PASS | FAIL` and `GO | NO_GO`
- no final output row is left in an `UNKNOWN` state
- docs point at the new authoritative command path instead of missing/no-op legacy surfaces
- targeted tests pass for the new orchestration and artifact-generation behavior

## Risks And Boundaries

The main risk is blending too much into one refactor.

If the work tries to redesign Stage 12 truth, Stage 13 truth, and Stage 14 at the same time, it will sprawl. The boundary here is narrower:

- restore the missing generation path
- keep Stage 12 and Stage 13 sequencing correct
- normalize final outputs
- retire the broken public entrypoints

Another risk is preserving compatibility stubs that keep misleading operators. If a legacy entrypoint is no longer authoritative, it should be removed or clearly replaced rather than left as a deceptive no-op.

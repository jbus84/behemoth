# Monthly Build / Recert Split Design

Date: 2026-03-26

## Goal

Split the current monthly certification flow into two explicit commands:

- `monthly-build` prepares a frozen month-scoped candidate certification bundle
- `monthly-recert` runs the definitive certification gate against that built bundle

This removes the current contract bug where recertification points Stage 14 at a
post-promotion archive path that does not exist yet.

## Problem

Today `monthly-recert` does too many jobs at once:

- synchronizes candidate models
- runs JForex certification prerequisites
- points `full-stage14-cert` at
  `configs/research/governance/oco_history_dukascopy_candidate/<month>`

That last dependency is wrong. The `oco_history_dukascopy_candidate/<month>`
archive is only created by `promote-live`, so the recert gate is trying to
validate a promoted-history artifact before promotion has occurred.

This blurs three distinct concerns:

1. building month-scoped candidate artifacts
2. certifying those artifacts
3. archiving the certified month to promoted history

## Decision

Introduce a strict three-phase monthly flow:

1. `monthly-build`
2. `monthly-recert`
3. `promote-live`

The stage logic remains authoritative. `monthly-build` and `monthly-recert` are
operator commands that prepare and certify a month without changing the meaning
of Stage 13 or Stage 14 themselves.

## Artifact Model

There are three artifact tiers.

### 1. Mutable candidate inputs

These are the current working candidate artifacts:

- `configs/research/governance/oco_dukascopy_candidate/`
- `models/oco_dukascopy_candidate/`

They remain mutable and represent the current candidate state under evaluation.

### 2. Frozen candidate month certification bundle

`monthly-build` creates a month-scoped frozen bundle for certification, for
example:

- `configs/research/governance/oco_candidate_builds/<YYYY-MM>/`

This bundle contains the month-scoped artifacts that Stage 14 expects:

- per-symbol live lock JSON
- allowed-state CSVs
- locked-predictions parquet files when deployable

This directory is the authoritative input to `monthly-recert`.

It is not promoted history. It is a pre-promotion certification bundle.

### 3. Promoted history archive

`promote-live` archives a certified month to:

- `configs/research/governance/oco_history_dukascopy_candidate/<YYYY-MM>/`

This remains the immutable record of what was actually promoted.

## Command Responsibilities

### `monthly-build`

`monthly-build` is responsible for producing the frozen month-scoped candidate
bundle. It should:

- derive or accept `MODEL_MONTH`
- sync candidate model artifacts from `models/oco/` into
  `models/oco_dukascopy_candidate/`
- freeze current candidate governance into a month-scoped certification bundle
- fail hard if the month bundle cannot be produced completely

It should not run JForex certification.

### `monthly-recert`

`monthly-recert` is responsible only for definitive certification. It should:

- require an existing month-scoped certification bundle from `monthly-build`
- run `jforex-dukascopy-matrix`
- run `local-jforex-parity-matrix`
- run `full-stage14-cert`
- point Stage 14 at the frozen candidate month bundle, not the promoted archive
- print the final go/no-go summary

It should not rebuild the month bundle implicitly. If the bundle is missing, it
should fail with an explicit instruction to run `monthly-build`.

### `promote-live`

`promote-live` remains post-cert only. It should:

- verify the latest certification results for the month passed
- archive the certified month bundle into
  `configs/research/governance/oco_history_dukascopy_candidate/<YYYY-MM>/`
- print the restart reminder

It should not perform certification or generate mutable candidate artifacts.

## Stage Boundary

The stage process remains authoritative. This design does not make
`monthly-recert` a new certification stage. Instead:

- `monthly-build` prepares the month-scoped certification input
- `monthly-recert` orchestrates the existing release-critical certification path
- Stage 14 still validates a frozen month-scoped bundle

This preserves the repo direction that certification should be definitive while
keeping operator workflows explicit and fast to rerun.

## Data Flow

1. Candidate research/model artifacts exist in mutable candidate locations.
2. `monthly-build` freezes those into
   `configs/research/governance/oco_candidate_builds/<YYYY-MM>/`.
3. `monthly-recert` runs the JForex certification path against that frozen
   bundle.
4. If certification passes, `promote-live` archives the certified bundle to
   `configs/research/governance/oco_history_dukascopy_candidate/<YYYY-MM>/`.

## Error Handling

### `monthly-build`

Fail hard when:

- source candidate model artifacts are missing
- expected governance inputs are missing
- month-scoped locks cannot be frozen
- locked predictions cannot be generated for deployable symbols

### `monthly-recert`

Fail hard when:

- the month-scoped certification bundle does not exist
- required per-symbol files are missing from the bundle
- certification stages fail
- Stage 14 fails or cannot read the bundle

The error message should explicitly tell the operator whether the next action is
to rerun `monthly-build` or to fix a certification issue and rerun
`monthly-recert`.

### `promote-live`

Fail hard when:

- the latest cert results for the month are missing
- cert results are stale
- any critical certification checks failed
- the certified month bundle cannot be archived

## Testing

Add or update tests to cover:

- `monthly-build` producing the correct freeze command and output location
- `monthly-recert` refusing to run when the month bundle is missing
- `monthly-recert` passing the frozen month bundle path into `full-stage14-cert`
- `promote-live` archiving from the certification bundle into promoted history

Targeted integration verification should include:

- running `monthly-build` for a known month
- running `monthly-recert` against the built month without rebuilding
- running `promote-live` only after a passing certification result

## Migration

The existing `monthly-recert` behavior should be split without changing the
underlying stage commands more than necessary.

Recommended migration order:

1. add `monthly-build`
2. change `monthly-recert` to consume a built month bundle instead of using
   `oco_history_dukascopy_candidate/<month>`
3. update `promote-live` to archive the certified build bundle
4. update help text and operator docs

## Non-Goals

- Re-running all research/build stages 1 through 12 during recert
- Making `monthly-recert` mutate upstream research artifacts implicitly
- Making promotion part of certification
- Changing Stage 14 outcome semantics beyond the lock-bundle input boundary

# Plan: Migrate the Full OCO Pipeline From HistData to Dukascopy

## Summary

Treat Dukascopy as the new canonical tick source for the entire system, not just model training. The migration should rebuild the full Stage 1 to Stage 12 pipeline from Dukascopy ticks, validate the rebuilt artifacts in staging, then replace the current HistData-derived canonical artifacts and defaults.

Current facts that drive the plan:
- The active training/eval configs consume derived `tick_velocity` artifacts, not raw ticks directly.
- Raw-tick builders already support a configurable `--tick-root`.
- Current canonical defaults, docs, and Stage 12 parity language still point at `/Users/danielfisher/Desktop/tick` and “HistData”.
- Dukascopy coverage is currently only `EURUSD` `201801-201806`, so this is a migration program to execute once all six symbols and the required date range are available.

## Key Changes

### 1. Make Dukascopy the canonical raw feed
- Fill `/Users/danielfisher/Desktop/dukascopy_ticks` for all active symbols and the full required history window used by the current research configs.
- Add a source-completeness audit step that verifies symbol-month coverage before any rebuild begins.
- Change canonical raw-feed defaults in Stage 1 builders and Stage 12 replay/parity tooling from `/Users/danielfisher/Desktop/tick` to `/Users/danielfisher/Desktop/dukascopy_ticks`.

### 2. Rebuild the full artifact chain in staging before promotion
- Build Dukascopy-derived artifacts into staging roots first, not directly into the current canonical roots:
  - `data/global_tickbars_dukascopy_candidate`
  - `data/analysis/tick_velocity_dukascopy_candidate`
  - `data/analysis/tick_opportunity_mining_dukascopy_candidate`
- Clone the active experiment configs so `dataset_dir`, candidate outputs, reports, and downstream artifact paths point to the staging Dukascopy roots.
- Re-run the full chain there:
  - Stage 1 bars and velocity
  - Stage 2 mining
  - Stage 3 monthly WFO
  - Stage 4 stop-limit realism
  - Stage 5 reduced-core rolling
  - Stage 6 tick-exact
  - Stage 8 robustness
  - Stage 9 governance/docs outputs
  - Stage 12 API parity using Dukascopy as truth
- Keep HistData artifacts untouched during staging; the final state is still direct replacement, but the build process should not partially overwrite canonical outputs.

### 3. Replace HistData-specific parity semantics with source-neutral or Dukascopy semantics
- Update Stage 12 docs and execution-parity language so Dukascopy is the canonical replay/parity feed.
- Replace HistData-specific script naming with source-neutral naming, and keep compatibility shims for existing call sites:
  - `replay_histdata_cbot_testclient.py` -> source-neutral replay runner
  - `validate_histdata_ctrader_execution_parity.py` -> source-neutral execution parity validator
- Preserve `--tick-root` as the main feed selector, but change the default to Dukascopy and update report text/check names so they no longer claim HistData truth.
- Update docs that currently hard-code HistData as canonical Stage 12 truth.

### 4. Promote Dukascopy outputs into canonical roots after green validation
- Archive the existing HistData-derived canonical artifacts and configs to a dated backup location.
- Promote the validated Dukascopy staging outputs into the canonical roots currently used by the pipeline:
  - `data/global_tickbars`
  - `data/analysis/tick_velocity`
  - `data/analysis/tick_opportunity_mining`
- Update the canonical experiment configs and docs so the default system path now refers to Dukascopy-backed artifacts.
- Regenerate strategy bible snapshots, operator/remediation reports, docs contract outputs, and mkdocs outputs from the Dukascopy-backed run.

## Public Interfaces / Config Changes

- Raw tick default root changes from `/Users/danielfisher/Desktop/tick` to `/Users/danielfisher/Desktop/dukascopy_ticks` in builder/parity tooling.
- Stage 12 replay/validation interfaces remain `--tick-root` based, but the default feed and report wording change to Dukascopy.
- HistData-specific Stage 12 script names become deprecated wrappers around source-neutral replacements to avoid breaking existing make targets/tests immediately.
- Canonical experiment configs are updated so `dataset_dir` and downstream artifact references resolve to the promoted Dukascopy-backed canonical roots after cutover.

## Test Plan

- Data audit:
  - verify all six active symbols exist in Dukascopy root for the required training/eval months
  - verify monthly parquet schema and UTC timestamp handling
- Staging pipeline validation:
  - targeted tests for any renamed/generalized Stage 12 scripts
  - targeted tests for Stage 1 builders if defaults change
  - rerun the full Dukascopy staging pipeline for all active symbols
- Acceptance gates before promotion:
  - relevant targeted tests pass
  - Stage 12 parity passes using Dukascopy truth
  - docs contract passes
  - `mkdocs build` passes
  - no missing Stage 9 predeploy/governance coverage for active symbols
  - no unresolved high/critical blockers in operator/remediation outputs
- Post-promotion validation:
  - rerun key health-check tests against canonical paths
  - confirm canonical docs/reports now reference Dukascopy instead of HistData where appropriate

## Assumptions

- Final state is a direct replacement: Dukascopy becomes the sole canonical feed for research, replay, and execution parity.
- Migration scope is the full pipeline rebuild, not just monthly WFO retraining.
- HistData artifacts are retained only as archived historical backups, not as an active parallel research path.
- The migration should not begin until Dukascopy coverage is complete for all active symbols and the full required history window.
- Staging roots are used only as a safe build-and-validate step before canonical promotion, not as a long-term shadow environment.

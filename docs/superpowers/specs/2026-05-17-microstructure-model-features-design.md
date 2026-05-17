# Microstructure Columns as Model Features + Importance Audit

**Date:** 2026-05-17
**Status:** Approved (design)

## Problem

Mining Phase 1 (PR #178) introduced six microstructure signals and uses them
to gate which candidate regimes survive into the ml-ready dataset. The
CatBoost tick-opportunity model never sees them. In
`build_tick_opportunity_ml_dataset.py` they are listed as
`_MICROSTRUCTURE_DIAGNOSTIC_COLS` and explicitly commented "preserved for
diagnostics; not consumed by model". The WFO trainer's `_feature_cols`
(`run_tick_opportunity_monthly_wfo.py:256`) trains on 16 columns — 13 market
features plus 3 structural parameters (`bar_ticks`, `horizon`,
`barrier_pips`).

The result: mining selects a regime *because* it is (e.g.) a tick-burst /
high-flow regime, then the model predicts inside that gated population blind
to the signal that selected it. The model cannot learn finer thresholds
within a mined regime.

A second gap: there is no audit of which of the existing 13 market features
actually carry weight, so feature expansion is unguided.

## Goals

- Promote the 5 numeric microstructure columns to model features.
- Keep them only if a walk-forward (WFO) run does not regress against the
  current baseline.
- Produce an importance + orthogonality audit report that informs future
  (separate) feature expansion.

## Non-Goals

- No change to mining or selection gate logic.
- `session_marker` is **not** added in this work (see Design §1).
- No new features beyond the 5 microstructure columns — expansion driven by
  the audit is a separate follow-up plan.
- No change to the 13 market features or 3 structural parameters.

## Design

### 1. Promote 5 microstructure columns to features

The 5 numeric columns — `tick_burst_score`, `quote_revision_rate_z`,
`directional_persistence_8`, `signed_flow_24`, `vol_cluster_score` — are
already z-scored numerics. They are added to `_feature_cols` in both
`run_tick_opportunity_monthly_wfo.py` and
`build_tick_opportunity_ml_dataset.py`. They flow through the existing
`_safe_numeric` coercion (`run_tick_opportunity_monthly_wfo.py:434-435`) and
`model.fit(tr[feats], ...)` (`:486`) with no special handling. The model
feature count goes 16 → 21 (13 market + 5 microstructure + 3 structural).

`session_marker` is **excluded**. It is the only categorical of the six, so
it would need `cat_features=` wiring at the `model.fit` call plus exclusion
from the numeric coercion loop. More importantly it is largely a function of
`hour_utc`, which is already a feature — so it likely fails the orthogonality
bar. Task 2's audit measures `session_marker` vs `hour_utc` correlation and
reports a verdict; if orthogonal it becomes a clean follow-up.

The `_MICROSTRUCTURE_DIAGNOSTIC_COLS` handling in
`build_tick_opportunity_ml_dataset.py` is updated so the 5 promoted columns
are not double-counted (carried once, as features); `session_marker` remains
a diagnostic column.

### 2. Acceptance gate — WFO must not regress

WFO runs twice: once on the current 16-feature baseline, once with the 5
microstructure features added. The 5 are kept only if the new run's WFO
verdict (monthly PASS rate and net pips) is no worse than baseline.

On regression:

1. Rank the 5 new features by `mean_imp` (mean feature importance).
2. Drop the lowest-importance one; re-run WFO.
3. Repeat until the verdict is at or above baseline.

The kept set is whatever survives. The 13 market features and 3 structural
parameters are never dropped — only the 5 new columns are on the chopping
block.

WFO is a slow integration run and needs the rebuilt velocity dataset, so the
baseline-vs-new comparison executes only once the Stage 0 data download
finishes. The Task 1 code change and its unit tests can land before then.

### 3. Importance + orthogonality audit

The WFO already emits per-month `{symbol}_feature_importance_{month}.csv`
files and a `mean_imp` aggregate. A small generator reads those plus a Pearson
correlation matrix computed over the feature columns of the ml-ready parquet,
and writes `docs/analysis/eurusd_feature_importance_audit.md` with three
sections:

- **Ranked mean importance** — all model features, highest to lowest.
- **Dead-weight flags** — features whose mean importance is below a floor.
- **Orthogonal expansion candidates** — areas to expand, flagged orthogonal
  (low correlation) to existing high-importance features; includes the
  explicit `session_marker` vs `hour_utc` verdict.

The report is informational only. Adding any new feature it recommends is a
separate follow-up plan.

## Error Handling

`_feature_cols` filters with `if c in df.columns`, so on older parquets
lacking microstructure columns the model silently trains on fewer features —
the silent-degradation mode PR #184 was built to kill. The plan adds a guard:

- **None of the 5 present** — raise a clear error pointing at
  `make rebuild-all` (stale Stage 0 data).
- **A subset missing** — a genuine schema-version split: log a warning naming
  the absent columns; do not crash.

## Testing

- `_feature_cols` is a pure function — unit-tested in both modules: with a
  frame containing all columns, the 5 microstructure columns appear in the
  result; without them, they do not, and the structural parameters still do.
- The "none present" guard is unit-tested to assert it raises.
- WFO itself is not unit-tested (slow integration run). The baseline-vs-new
  comparison is the verification, run manually once data is available — the
  same manual-verification posture used for the Makefile changes in PR #184.

## File Map

- `scripts/run_tick_opportunity_monthly_wfo.py` — add 5 columns to
  `_feature_cols` (`:256`); add the missing-column guard.
- `scripts/build_tick_opportunity_ml_dataset.py` — add 5 columns to
  `_feature_cols` (`:258`); update `_MICROSTRUCTURE_DIAGNOSTIC_COLS` handling
  so promoted columns are not double-counted.
- `tests/` — unit tests for both `_feature_cols` functions and the guard.
- Audit generator — new or appended script producing
  `docs/analysis/eurusd_feature_importance_audit.md`.

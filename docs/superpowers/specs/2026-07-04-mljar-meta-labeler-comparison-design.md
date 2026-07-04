# mljar-supervised Meta-Labeler Comparison — Design

## Context

The reversion-OCO strategy's meta-labeler (second-stage classifier deciding whether
to hold or reject each fill) has always used `sklearn.ensemble.
HistGradientBoostingClassifier` with default-ish settings, fit fresh per WFO fold.
Nothing about the classifier itself has ever been questioned or compared against
alternatives — every improvement to date (PR #376, PR #377) came from a better
upstream sigma signal feeding the same classifier, never from the classifier itself.

`mljar-supervised` is an AutoML library that trains multiple model families
(LightGBM, Xgboost, CatBoost, Random Forest, Extra Trees, Neural Network, etc.),
combines them via ensembling/stacking ("model mixing"), and produces a leaderboard
+ explainability reports. It's a plausible way to both (a) get a stronger
classifier via mixing multiple model families, and (b) understand which model
family actually fits this data best — something never checked before.

A real constraint: `mljar-supervised`'s `AutoML` class defaults to a 1-hour time
budget and tries ~10 model families plus ensembling/stacking. Our meta-labeler
refits fresh per WFO fold (5 folds per pair). Naively wiring in AutoML's defaults
across even one pair would risk multi-hour runtimes; across 4 pairs, this could be
20+ hours — clearly impractical given today's session already hit real friction
with multi-minute-to-hour-long sweeps.

## Goals

1. Compare `mljar-supervised`'s `AutoML` (fast mode, capped time budget) against
   the existing `HistGradientBoostingClassifier` meta-labeler, on the identical
   trade population and WFO fold splits, for a fair apples-to-apples test.
2. Surface which individual model family (not just the ensemble) actually performs
   best on this data via `AutoML`'s leaderboard — genuine new information about
   what kind of model fits FX meta-labeling best.
3. Keep this fully additive and cheap to discard: no changes to
   `meta_label_straddle.py`'s `fit_meta_label_wfo`, no `pyproject.toml`/`uv.lock`
   changes (ephemeral dependency via `uv run --with`).

## Non-goals

- Not replacing the production meta-labeler outright — this is a comparison, and
  only becomes a real proposal to adopt if it clearly wins.
- Not running mljar's heavier modes (`Perform`, `Compete`, `Optuna`) or its full
  SHAP-based explainability (`explain_level=2`) — scoped to `mode="Explain"` (the
  fastest mode) with a capped `total_time_limit` and leaderboard-level
  introspection (`get_leaderboard()`) only, per the approved design conversation.
- Not scaling to all 4 pairs in this first pass — EURUSD only, to keep the
  exploration cheap and fast; scaling up is an explicit follow-up decision after
  seeing whether mljar shows any real signal at all.
- Not adding `mljar-supervised` to `pyproject.toml`/`uv.lock` — stays ephemeral
  (`uv run --with mljar-supervised`) unless a follow-up decision commits to it.
- Not adding new pytest coverage — matches this codebase's existing pattern for
  `scripts/boostlss_xs/` research scripts (informal validation: run it, inspect
  the printed table).

## Architecture

### `scripts/boostlss_xs/mljar_meta_labeler_compare.py` (new)

Reproduces the current best trade population using existing, unmodified functions:
1. `fit_wfo_quantile_robust(X, y, quantile=0.90)` (from `plain_regression_baseline.py`)
   for the high-quantile sigma signal, and a second call at `quantile=0.5` for the
   low/median leg (matching `tail_shape_feature.py`'s pattern exactly).
2. `run_tick_backtest(..., sigma_override=sg_high, sig_thresh=4.5,
   sig_thresh_hi=5.5)` for the tick-exact trade population.
3. Post-hoc timestamp join to merge `tail_ratio = sg_high / max(sg_low, 1e-6)`
   onto the trades dataframe, identical to `tail_shape_feature.py`'s approach.

Then, instead of calling `fit_meta_label_wfo` (which only fits
`HistGradientBoostingClassifier`), this script implements its own WFO fold loop —
same 5-fold expanding-window structure, same fold boundaries (`n // (N_FOLDS + 1)`
per fold, no embargo — matching `fit_meta_label_wfo`'s existing behavior exactly so
the comparison is apples-to-apples) — but at each fold fits **both**:
- The baseline: `HistGradientBoostingClassifier` (same params
  `fit_meta_label_wfo` uses today).
- mljar: `AutoML(mode="Explain", total_time_limit=90, algorithms=["LightGBM",
  "Xgboost", "CatBoost", "Random Forest", "Extra Trees"], results_path=<per-fold
  scratch tempdir>, verbose=0)`.

Both get `predict_proba` on the identical held-out fold rows. Collects both sets of
OOS probabilities across all 5 folds, computes AUC/TP%/Option B bps/fill for each
using the existing `_option_b_net_per_fill` — printed side by side.

After all folds, one representative fold's `AutoML.get_leaderboard()` output is
printed to show which individual algorithm family won (not just the ensemble),
answering "is boosting really best here, or would a different family do better?"

`results_path` is set to a fresh subdirectory under `/tmp/mljar_meta_compare/`
per fold (not committed, not written into the repo) to avoid polluting the repo
with AutoML's generated model artifacts and reports.

## Error handling

- Same defensive patterns as every other script in this investigation: NaN-guard
  the `tail_ratio` denominator (`np.maximum(sg_low, 1e-6)`), skip folds with too
  few rows (matching `fit_meta_label_wfo`'s implicit fold-size behavior).
- If `AutoML.fit()` raises for a given fold (e.g. too few rows for a stable model
  search), log the failure with the fold index and skip that fold's mljar
  contribution — following PR #377's fix (log, don't silently suppress).
- No new error paths in shared production code — this script only reads from
  existing functions.

## Testing

- No new pytest coverage.
- Script must run end-to-end on EURUSD within a bounded time (5 folds × 90s ≈
  7.5 minutes, plus tick-exact backtest time already established as fast at this
  scope from prior scripts) and print a clean comparison table plus one
  leaderboard.
- Findings recorded into `scripts/boostlss_xs/BACKLOG.md`, continuing this
  investigation's established format.

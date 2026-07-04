# BoostLSS Signal Improvements — Design

## Context

PR #376 (merged) established a new best sigma signal for the reversion-OCO strategy:
quantile-robust regression (`HistGradientBoostingRegressor`, `loss="quantile"`,
`quantile=0.85`, predicting `|next-bar return|` directly instead of any BoostLSS
distributional family) run through the exact same tick-exact + meta-labeler pipeline,
with a **windowed** sigma filter (`sig_thresh` lower bound AND `sig_thresh_hi` upper
bound, excluding anomalously large predicted-sigma bars that are more likely to be
jump/news events the strategy's reversion thesis says will fail).

Best single point found: `sig_thresh=4.5, sig_thresh_hi=5.5` → +5.292 bps/fill. More
importantly, a **broad plateau** of +4.8 to +5.3 bps/fill across roughly
`sig_thresh∈[4.0,4.5], sig_thresh_hi∈[4.8,5.5]` — 5-6x Gaussian's original tuned
baseline (+0.896 bps/fill), with meta-labeling completely untouched throughout.

This work was exploratory (background sweeps, iterative refinement) and the plateau
was found on the pooled 4-pair aggregate only. Before building further on top of it,
this project (1) confirms the finding is real and not concentrated in one pair/period,
then (2) looks for a better base signal (quantile level), then (3) adds one genuinely
new, purely additive feature to the meta-labeler.

## Goals

1. **Stability check**: confirm the windowed quantile-robust plateau holds up
   consistently across pairs and years, not just in the pooled aggregate.
2. **Quantile level sweep**: only q=0.85 has been tested for the regressor itself.
   Determine if a different quantile level raises the whole baseline.
3. **Tail-shape meta-labeler feature**: fit a second, lower quantile (e.g. q=0.5) per
   pair alongside the existing high quantile, expose their ratio to the meta-labeler
   as a new feature (analogous to what SHASH's `nu`/`tau` or Merton's `lam` were
   reaching for, but via quantile regression instead of a joint likelihood — avoiding
   all the boostlss convergence instability found in PR #376).

## Non-goals

- Not re-tuning `entry_k`/`sl_k` — deferred, tracked in BACKLOG.md, separate work.
- Not adding richer features to the sigma regressor itself (cross-pair breadth,
  longer-lookback vol) — a bigger, separate effort.
- Not touching the existing meta-labeler's core logic, the tick-exact simulation, the
  cost model, or `run_tick_backtest`'s signature — the tail-shape feature is merged
  onto trade rows via a post-hoc join by timestamp in the new investigative script,
  not a change to shared production code.
- Not adding pytest coverage — matches this codebase's existing pattern for
  `scripts/boostlss_xs/` research scripts (informal validation: run it, inspect the
  printed table).

## Architecture

### 1. Stability check (`scripts/boostlss_xs/stability_check.py`, new)

Reuses `fit_wfo_quantile_robust` (from `plain_regression_baseline.py`) to compute
sigma once per pair, cached. Runs `run_tick_backtest` with the chosen window
(`sig_thresh`, `sig_thresh_hi` — parameterized, defaulting to the PR #376 sweet spot)
per pair, but reports results **broken down by pair** (not just pooled) and **by
year** (post-hoc groupby on the `ts` column of the trades dataframe, matching the
existing `_print_summary`'s "By year" table pattern in `meta_label_straddle.py`).

Acceptance: if every pair is individually net-positive and no single year dominates
the pooled average, the plateau is confirmed robust. If one pair or one year is
carrying the whole result, that's a real, reportable finding on its own — not a
failure of the script.

### 2. Quantile level sweep (`scripts/boostlss_xs/quantile_level_sweep.py`, new)

For each candidate quantile level in `{0.70, 0.75, 0.80, 0.85, 0.90, 0.95}`, fits sigma
once per pair (`fit_wfo_quantile_robust(X, y, quantile=q)`), then tests it at a small,
fixed set of representative windows (not a full grid — keeps this bounded) chosen to
straddle the PR #376 sweet spot, e.g. `(sig_thresh=4.0, sig_thresh_hi=5.0)` and
`(sig_thresh=4.5, sig_thresh_hi=5.5)`. Reports the same metrics table as
`sigma_window_sweep.py` (n_trades, AUC, TP%, Option B bps/fill) per
(quantile, window) combination.

### 3. Tail-shape meta-labeler feature (`scripts/boostlss_xs/tail_shape_feature.py`, new)

Per pair: fits **two** quantile regressions via `fit_wfo_quantile_robust` — the
existing high quantile (whatever phase 2 determines is best, defaulting to 0.85) and
a new low/median quantile (q=0.5). Computes `tail_ratio = high_pred / max(median_pred,
floor)` at every OOS bar position (floor e.g. `1e-6`, matching the defensive-floor
convention used throughout `distributions.py`'s NLL functions).

Runs `run_tick_backtest` as usual with the high quantile as `sigma_override` (sizing
unchanged). After getting the trades dataframe back, merges `tail_ratio` onto it by
matching each trade's `ts` to the bar index the ratio was computed at (a simple
dict-based lookup or pandas merge on the timestamp strings already present in both
the trades dataframe and the per-bar feature dataframe — same join key pattern
`run_tick_backtest` itself already uses internally to merge `feat_df` onto trades).

Compares meta-labeler AUC / Option B **with** `tail_ratio` added to `_FEAT_COLS` vs.
**without** (baseline), holding the window and primary quantile level fixed at
whatever phases 1-2 determine to be the best config. This directly tests whether
tail-shape information helps the *second* stage (trade quality classification) even
though earlier work showed it doesn't help when baked into first-stage sigma sizing.

## Error handling

- `tail_ratio`'s denominator (median-quantile prediction) is floored before division
  to avoid `inf`/`nan` — same defensive pattern as `np.maximum(sigma, 1e-10)` used
  throughout `distributions.py`.
- NaN sigma predictions from WFO fold warmup are filtered using the same
  `~np.isnan(...)` conventions already used everywhere else in this codebase.
- No new error paths in shared production code — all three new scripts are additive,
  read-only consumers of existing functions (`fit_wfo_quantile_robust`,
  `run_tick_backtest`, `fit_meta_label_wfo`, `_option_b_net_per_fill`).

## Testing

- No new pytest coverage (matches existing pattern for this codebase's research
  scripts).
- Each script must run end-to-end without crashing and produce a printed comparison
  table, `make quality` clean before committing.
- Findings get written into `scripts/boostlss_xs/BACKLOG.md`, continuing the format
  established in PR #376's writeup.

# FX Tail-Edge Walk-Forward Confirmation — Design

**Date:** 2026-06-18
**Status:** Approved (design), pending implementation plan
**Script (target):** `scripts/fx_coint/tail_wfo.py`
**Builds on:** `scripts/fx_coint/reg_signal_hunt.py` (PR #340) — reuses `build_freq_bars`,
`build_panel`, the feature set, and the cost constants.

## Purpose

Confirm (or kill) the tail/cost-tier edge found in PR #340 by replacing the single 70/30
split with a **walk-forward** evaluation of a **long-only, top-decile** strategy, with
**decile-level significance net of real cost**. See memory:
`project_fx_intraday_tail_cost_tier_edge`.

The PR #340 result (top-decile long net-positive on tight-cost majors at 2–3h, hit 56–62%)
is the *floor* from a single split with an in-sample decile threshold. This script tests
whether it survives proper out-of-sample walk-forward and is statistically real.

## What it must fix vs the #340 diagnostic

1. **No-look-ahead decile gating.** The top-decile threshold must be derived from the
   **train fold's** predicted distribution and then applied to test predictions. (#340's
   `decile_table` took percentiles on the test set — fine as a diagnostic, mild look-ahead
   for a strategy.)
2. **Walk-forward, not one split.** Expanding-window WFO: refit Ridge each fold, predict
   the next contiguous block, roll forward; concatenate out-of-sample trades across folds.
3. **Long-only.** Trade only when test prediction ≥ train-derived top-decile threshold →
   go long one bar → net = realized return − round-trip cost. (Short side was broken in #340.)

## Universe & horizons

- **Tight-cost majors:** EURUSD, GBPUSD, USDJPY (costs 0.64/0.63/0.80 bps). Primary.
- **USDCAD** included as a secondary test (3h long was +2.22 in #340 despite 0.97 cost).
- **USDJPY 3h is reverting, not continuation** — flag it: run it both long-only (expected
  to fail) and as a separate short-the-bottom-decile variant; report separately, do not
  pool its sign with the others.
- Horizons: **2h and 3h** (1h is dead; 4h noisy).

## Walk-forward protocol

- Expanding window. Initial train = first `min_train` bars (e.g. 60% of panel); test block
  = next `test_block` bars (e.g. ~3 months at the freq); roll by `test_block`; refit each step.
- Purge gap of 1 bar between train and test (next-bar target).
- Per fold: fit Ridge on train, compute `q = quantile(train_preds, 0.9)` (top-decile
  threshold), select test bars with `pred ≥ q`, record their `(net_return = actual_bps − cost)`,
  entry hour, and fold id.

## Statistics & outputs

Per (pair, freq, side):
- `n_trades`, `mean_net_bps`, `std`, `t_stat` (one-sample t on per-trade net), `p_value`.
- `pos_fold_pct` (fraction of folds with positive mean net) — robustness, not just pooled mean.
- `total_net_bps`, `hit_rate`.
- Net IC-by-entry-hour of the selected trades.

Across the cell family (pairs × freqs × sides): **BH-FDR** on the p-values.

**Go/no-go gate:** a cell is confirmed only if `mean_net_bps > 0` AND **BH-significant** AND
`pos_fold_pct ≥ 0.6` (edge present in a majority of folds, not one lucky window).

## Decision rules to report (all long-only unless noted)

- **Top-decile (q=0.9 train threshold)** — primary.
- **Sensitivity:** also q=0.8 (top quintile) and q=0.95, to confirm monotonicity (more
  conviction → higher net) rather than a single-threshold artifact.

## Outputs

`scripts/fx_coint/tail_wfo_results.md`: the per-cell table, the BH verdict, the q-sensitivity
table, and a clear GO/NO-GO. If GO, the next step is tick-exact maker/taker fill verification.

## Out of scope (YAGNI)

Richer features/models (this still uses the 5 price-only features — a richer model is a
*later* lift only if the floor confirms); cross-symbol pooling; tick-exact fills; position
sizing beyond unit-per-trade.

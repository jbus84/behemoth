# FX reversion-conditioner null-test (Step 0)

**Date:** 2026-06-16
**Status:** design approved, pre-implementation
**Predecessors:**
- `docs/analysis/fx_usd_factor_residual_STALE_BAR_KILL.md` — intraday price-residual
  reversion gross ~0.3–0.5 bps, sub-cost.
- `docs/analysis/fx_flow_factor_deviation_ic.md` — quote-flow deviation ~35× sub-cost.

## Objective

Before building any selection model, answer one question with honest OOS evidence:
**is a candidate fade trade's forward reversion predictable ex-ante from anything other
than displacement size?** If no feature carries that information, no model can, and we
stop. If something does, it justifies a walk-forward selection model (a later, separate
step). The unconditional fade is sub-cost (~+0.4 bps gross < ~0.7 bps cost); the only way
a "tool" helps is if a conditioner predicts *higher conditional reversion* on a
selectable subset.

## The core guard: magnitude vs signed-fade

Two different predictabilities, reported **separately** against every feature:

- **`|forward_move|`** (magnitude) — almost certainly predictable (volatility clusters).
  **Worthless alone**: a big move with coin-flip sign loses the spread symmetrically.
- **`signed_fade`** (the alpha) — does the residual actually *revert*, signed. This is
  the only thing that matters.

A feature that predicts `|forward_move|` but not `signed_fade` is a decoy, not a signal.
Displacement **size** is already known to anti-predict reversion (big moves are
information; win-rate ~49%), so size is the null we must beat.

## Universe & target

- **Bars:** honest 30m raw-tick bars, 6 USD majors, 2018–2026 (`*_30m_raw.parquet` and a
  30m feature panel aggregated from the existing 1-min flow bars).
- **USD-factor residual:** orient each pair's 30m log-return to USD strength, factor =
  cross-pair mean (estimation-free), residual = oriented return − factor (the
  displacement), per the validated decomposition.
- **Candidate trades:** bars where `|oriented residual|` is above its causal rolling
  median (a genuine dislocation).
- **Target — forward fade gross**, 1-bar (30m) hold:
  `signed_fade = −sign(residualₜ) · oriented_return(t→t+1) · 1e4` (bps). What a fade trade
  earns before cost.
- **Decoy target:** `abs_move = |oriented_return(t→t+1)| · 1e4` (bps).

**Lookback defaults** (pin these; tune only inside IS if ever needed): `k = 4` bars (2h)
for cumulative residual / speed / momentum; trailing realized-vol and tick-intensity
z-score window = `16` bars (8h).

## Feature panel (causal, ≤ t; aggregated from 1-min flow bars → 30m)

- **Displacement:** `|residual|`, `sign(residual)`, cumulative residual over last k bars,
  residual speed (Δresidual).
- **Vol / liquidity state:** realized vol (std of 1-min log-returns in a trailing
  window), current spread (bps), tick intensity (`n_ticks` and its causal z-score).
- **Cross-pair structure:** basket dispersion (Σ|residual| across the 6 pairs), count of
  pairs co-dislocated, factor-share vs residual-share of total oriented move.
- **Flow:** `flow_ofi`, `flow_tick` (aggregated to 30m).
- **Calendar & momentum:** hour-of-day, day-of-week, own-pair return over last k bars.

All features use only information available at or before `t`; the target is strictly
forward.

## Null-test metrics

1. **Univariate** — for each feature: Spearman IC and mutual information vs `signed_fade`
   **and** vs `abs_move`, computed **IS (2018–2022) / OOS (2023–2026)**. BH-FDR over the
   `signed_fade` univariate tests.
2. **Joint** — a regularized model (ridge and/or shallow gradient boosting) trained on IS
   predicting `signed_fade` from all features; report **OOS IC and R²** of predicted vs
   actual `signed_fade`. This is the real question: does the feature *set* predict the
   signed edge OOS.
3. **Top-quantile economics** — rank OOS candidate bars by the joint model's predicted
   `signed_fade`; report the **mean gross fade of the top decile/quintile vs the ~0.7 bps
   cost**, with trade count. Does conditioning plausibly clear the wall?

Baselines reported alongside: unconditional mean `signed_fade`; the size-conditioned
selection (the known-failing null).

## Gate verdict (set in advance)

- **PROCEED** to a walk-forward selection model only if `signed_fade` is predictable OOS
  (stable IS→OOS sign, FDR-significant univariately or joint OOS R² > 0) **and** the
  top-quantile OOS gross approaches or exceeds ~0.7 bps cost.
- **STOP (NO-GO)** if `signed_fade` is unpredictable OOS — even when `abs_move` is
  predictable. That pinpoints the failure mode: magnitude predictable, direction not, so
  no tool clears cost.

The honest prior, given the thread, is STOP; the value is a clean, falsifiable answer.

## Deliverables

- `scripts/fx_coint/build_feature_bars_30m.py` — aggregate 1-min flow bars to a 30m
  feature panel (cached).
- `scripts/fx_coint/reversion_conditioner_nulltest.py` — compute the residual, targets,
  features, and all null-test metrics; print tables.
- `docs/analysis/fx_reversion_conditioner_nulltest.md` — univariate ICs (signed vs
  magnitude, IS/OOS), joint OOS predictive power, top-quantile gross-vs-cost, gate
  verdict.
- **No selection model or strategy in this step.**

## Reuse / dependencies

- Reuses the cached 1-min flow bars (`data/tick_bars/{sym}_1m_flow.parquet`) and the
  tested kernels (`usd_flow_factor.usd_factor_residual`, `flow_metrics`,
  `flow_proxies.causal_zscore`).
- Mirrors the look-ahead discipline of the raw-tick work; no tick-count→time resampling.
- Implementation runs in the current git worktree (PR #334 thread).

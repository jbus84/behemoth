# Cross-Symbol Family A — Dollar-Factor Residual

**Date:** 2026-05-21
**Status:** Approved (design)
**Roadmap:** Family A on top of `2026-05-19-cross-symbol-alignment-design.md`
(infrastructure landed as PR #192).

## Problem

The single-symbol mining families look at each major's own path. The
cross-symbol alignment infrastructure (PR #192) now exposes peer returns
and three USD-strength market measures (`mkt_all6`, `mkt_loo`, `mkt_pca`)
on every target bar. This sub-project consumes that infrastructure to mine
the first of three planned cross-symbol families.

**Hypothesis:** at any bar, a symbol's USD-aligned return decomposes into
a common USD-factor component plus an idiosyncratic residual. When the
residual is extreme — the target moved *much more than the dollar move
predicted* — the move is often an overshoot that fades over the next few
bars. The trade is contrarian to the residual.

## Goals

- A new `dollar_residual` mining family that consumes
  `build_cross_symbol_frame`.
- Strictly look-ahead-free beta and residual-σ estimation (trailing window
  only).
- Each candidate scored against the same random-entry baseline that the
  single-symbol families use.

## Non-Goals

- No changes to existing families, the WFO, the ml-dataset, or the
  selection pipeline.
- No families B (dispersion) or C (lead-lag) — they are separate PRs.
- No clock resampling — alignment is the tick-native one PR #192 provides.

## Design

### 1. Decomposition

For each target bar `t`:

- Let `r_t = ret_z` of the target (USD-aligned).
- Let `m_t = mkt_loo[t]` — the equal-weighted mean of the 5 peer
  USD-aligned returns, computed in PR #192.
- Fit a rolling OLS on the trailing `residual_window` bars `(r, m)`:
  `r = alpha + beta * m + eps`.
- The point estimate uses bars `[t - residual_window, t)` only — the bar
  at `t` is **excluded** from its own fit.
- The residual at `t` is `eps_t = r_t - alpha_t - beta_t * m_t`.

`mkt_loo` is used (not `mkt_all6`) because including the target in its own
benchmark mechanically shrinks the residual by ~1/6 — see the alignment
design doc §4.

### 2. Standardisation and threshold

Residuals are standardised by their own rolling σ on the same trailing
window: `z_t = eps_t / sigma_t`. The candidate enters when `|z_t|`
exceeds a threshold:

- `z_t > +threshold` → enter short (`side = −1`): residual is unusually
  positive, bet on reversion down.
- `z_t < −threshold` → enter long (`side = +1`).

### 3. Param grid

`param_grid` yields `(horizon, residual_window, threshold_z)`:

- `residual_window ∈ {200, 500}` bars
- `threshold_z ∈ {1.5, 2.0, 2.5, 3.0}`
- horizons from `cfg["horizons"]`

8 (residual_window × threshold) × horizons combos per regime.

### 4. Outcome

For each entry index `i` and chosen `side`:
`gross = side * y_fwd_pips_h{horizon}[i]`.

Identical outcome contract to `directional` / `directional_run`.

### 5. Family hooks

- `entry_indices(frame, regime_mask, params)` — lazily builds the
  cross-symbol frame for `(symbol, bar_ticks)` once (cached), aligns it to
  the supplied `frame` by `close_ts`, computes rolling alpha/beta/σ on the
  trailing window, returns the regime-masked indices where `|z| ≥
  threshold`.
- `measure_gross(frame, entries, params)` — looks up `y_fwd_pips_h{h}`
  and the sign of `−z` at each entry to return `side * y`.
- `candidate_metadata` — `family = "dollar_residual"`;
  `state_id = "dollar_residual__{regime}__w{window}_z{threshold:.1f}"`;
  `regime_desc = "{regime};window={window};z={threshold:.1f}"`;
  `ml_ready_target_type = "dollar_residual"`.

### 6. Context injection — minimal orchestrator change

The family needs `dataset_dir` and `horizons` to call
`build_cross_symbol_frame`; those live in `cfg`, not on `frame`. The
orchestrator already decorates per-family `params` with `symbol` and
`bar_ticks`; it now also injects `_dataset_dir` (str) and `_horizons`
(list[int]). The leading underscore signals "context, not a tuned axis";
other families ignore them.

### 7. Look-ahead discipline

- The rolling OLS fit at bar `t` uses only bars strictly before `t`. The
  cross-symbol frame's PCA factor already follows the same discipline
  (PR #192 §6); this family's regression layers on top.
- The σ estimate uses the same trailing window.
- No bar's `eps_t` or `z_t` is ever recomputed using later information.

### 8. Output routing

A new file `{SYMBOL}_dollar_residual_candidates.csv` per symbol. Not folded
into the existing `directional` output because the underlying signal
mechanism is structurally different (cross-symbol relative value vs.
own-bar direction).

### 9. Caching

`DollarFactorResidualFamily._cs_frame_cache` keyed by `(symbol, bar_ticks,
frame_fingerprint)` holds the assembled cross-symbol frame so the heavy
`build_cross_symbol_frame` + peer parquet I/O happens once per train/test
split. The family also caches the alpha/beta/σ arrays per
`(frame_fingerprint, residual_window)` so the threshold sweep is cheap.

## Testing

- **Registration** — `dollar_residual` satisfies `MiningFamily`; in
  `FAMILY_REGISTRY` and `_LIBRARY_TYPE_ALIASES["all"]`.
- **Trailing-window discipline** — perturbing future bars does not change
  earlier `eps` / `z` arrays.
- **Mechanics** — on a fabricated 6-symbol frame where the target is pure
  `+1.5σ residual` over a regime, the family produces short entries in
  that regime and no entries elsewhere.
- **No false edge** — on a noise-only 6-symbol fixture, candidates' gross
  EV sits within the random-entry baseline noise band.
- **Detects structure** — on a 6-symbol fixture where the target's
  positive residuals reliably revert, candidates score `z > 2`.

## Families B and C — outline only

Both consume `build_cross_symbol_frame` and will be separate
`docs/superpowers/specs/...-design.md` files when scheduled.

- **B — Cross-sectional dispersion.** Rank the 6 USD-aligned returns each
  aligned bar; the target is "extreme" when it sits at rank 1 or rank 6.
  Bet rank-1 (highest) → short, rank-6 (lowest) → long. Param: rank
  positions to treat as extreme; horizon.
- **C — Lead-lag follow.** When a peer's `xs_ret_z__{peer}` exceeds a
  trigger-σ threshold at bar `t−k`, enter the target at `t` in the same
  USD-direction. Param: which peer(s), lag bars, trigger-σ; horizon.

Both follow the same protocol/output/baseline pattern as family A.

## File Map

- `scripts/mining_family.py` — `DollarFactorResidualFamily`; register it;
  alias entries.
- `scripts/run_tick_opportunity_mining.py` — `_dataset_dir` /
  `_horizons` injection; output routing for the new CSV; library_type
  whitelist + `run()` return adjusted.
- `tests/test_mining_family.py` — registration, mechanics, trailing-window,
  no-false-edge, detects-structure.

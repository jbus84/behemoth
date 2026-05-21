# Cross-Symbol Family B — Cross-Sectional Dispersion

**Date:** 2026-05-21
**Status:** Approved (design)
**Roadmap:** Family B on top of `2026-05-19-cross-symbol-alignment-design.md`
(infrastructure landed as PR #192; family A landed as PR #199).

## Problem

Family A bets the *idiosyncratic residual* mean-reverts after a rolling
regression decomposition. Family B is the simpler cross-sectional cousin:
no regression, no factor model — just rank the 6 majors' USD-aligned
returns each bar and trade the extreme rank back toward the median.

**Hypothesis:** the symbol that moved *most* in either USD direction this
bar is most likely overextended and partially reverts over the next few
bars. The trade is contrarian to the rank extreme.

## Goals

- A new `dispersion_rank` mining family that consumes
  `build_cross_symbol_frame`.
- No rolling window, no fit — entry is a point-in-time rank check.
- Each candidate scored against the random-entry baseline (same as
  every other family).

## Non-Goals

- No regression / factor model — that is family A.
- No lag — that is family C.
- No clock resampling, no changes to existing families.

## Design

### 1. Per-bar rank

At each target bar `t`, the cross-symbol frame already exposes the
target's own USD-aligned return (computable from `ret_z` + `_USD_SIGN`)
and each peer's `xs_ret_z__{peer}` (USD-aligned, as-of joined). These 6
values are a coherent cross-section because the peer joins are backward —
no peer value depends on information after `t`.

Compute the per-bar rank of the target among the 6 (rank 1 = most
USD-positive move that bar, rank 6 = most USD-negative). Ties broken by
the symbol's lexical order (deterministic, doesn't favour the target).

### 2. Entry rule

Enter when the target's rank is in the top-`k` or bottom-`k`:

- `rank ≤ k` (target moved most USD-positive): expect mean reversion in
  USD-aligned terms → trade with `side_usd_aligned = −1`.
- `rank ≥ 7 − k` (target moved most USD-negative): trade with
  `side_usd_aligned = +1`.

The raw-price side flips through the target's USD sign:
`side_raw = side_usd_aligned * _USD_SIGN[target]`.

Concretely, for **EURUSD** (USD on the quote side, `_USD_SIGN = −1`):

- Rank 1 (USD strengthened most via EURUSD → EURUSD fell most): bet
  EURUSD reverts up → `side_raw = +1` (LONG EURUSD).
- Rank 6 (USD weakened most via EURUSD → EURUSD rose most): bet EURUSD
  reverts down → `side_raw = −1` (SHORT EURUSD).

For **USDJPY** (`_USD_SIGN = +1`) the signs are reversed:

- Rank 1: SHORT USDJPY.
- Rank 6: LONG USDJPY.

In both cases the trade fades the symbol's own raw price move — the
rank check just identifies the bars where that move was extreme
*relative to peers*, not extreme in absolute terms.

### 3. Param grid

`param_grid` yields `(horizon, rank_k)`:

- `rank_k ∈ {1, 2}` — `k=1` is "only the single extreme symbol per bar";
  `k=2` includes the second-most-extreme (more entries, weaker filter).
- horizons from `cfg["horizons"]`.

2 × horizons combos per regime. Smaller grid than family A because the
mechanism has fewer tunable knobs.

### 4. Outcome

`gross = side_raw * y_fwd_pips_h{horizon}[i]`. Same outcome contract as
`directional` / `dollar_residual`.

### 5. Family hooks

- `entry_indices(frame, regime_mask, params)` — builds the cross-symbol
  frame for `(symbol, bar_ticks)` (cached, same pattern as family A),
  ranks per bar, returns the regime-masked indices.
- `measure_gross(frame, entries, params)` — looks up `side_raw` at each
  entry and multiplies by `y_fwd_pips_h{h}`.
- `candidate_metadata` — `family = "dispersion_rank"`;
  `state_id = "dispersion_rank__{regime}__k{rank_k}"`;
  `regime_desc = "{regime};k={rank_k}"`;
  `ml_ready_target_type = "dispersion_rank"`.

### 6. Look-ahead discipline

- The peer joins in `build_cross_symbol_frame` are backward as-of
  (`direction="backward"`) — every peer value at target time `T` came
  from a bar that closed `≤ T`.
- The per-bar rank uses only bar-`t` columns — no rolling window needed.
- No bar's rank or side ever depends on a peer value from after `t`.

### 7. Output routing

A new file `{SYMBOL}_dispersion_rank_candidates.csv` per symbol. Not
folded into `directional` (different signal mechanism) or
`dollar_residual` (different decomposition).

### 8. Caching

Reuses the same cross-symbol frame cache pattern as family A — heavy
peer-parquet I/O happens once per `(symbol, bar_ticks, train/test
fingerprint)`. The rank computation itself is cheap.

## Testing

- **Registration** — `dispersion_rank` satisfies `MiningFamily`; in
  `FAMILY_REGISTRY` and `_LIBRARY_TYPE_ALIASES["all"]`.
- **Sign mechanics** — on a fabricated cross-section where the target is
  the unique rank-1, the family produces a contrarian-to-USD-direction
  entry; same fixture with target at rank-6 yields the opposite side.
- **No-op without context** — without `_dataset_dir` / `_horizons`
  injection (or with a non-cross-symbol target), the family returns
  empty arrays.
- **End-to-end smoke** — the 6-symbol synth fixture from
  `tests/test_tick_opportunity_mining.py::_build_synth_tick_velocity`
  drives the family through to completion without error.

## File Map

- `scripts/mining_family.py` — `DispersionRankFamily`; register it;
  alias entries.
- `scripts/run_tick_opportunity_mining.py` — output routing for the new
  CSV; library_type whitelist + `run()` return adjusted; main() writer.
- `tests/test_mining_family.py` — registration, sign mechanics, no-op,
  end-to-end smoke.

# Cross-Symbol Family C — Lead-Lag Follow

**Date:** 2026-05-21
**Status:** Approved (design)
**Roadmap:** Family C on top of `2026-05-19-cross-symbol-alignment-design.md`
(infrastructure landed as PR #192; family A as PR #199; family B as
PR #200).

## Problem

Families A and B both bet *against* extreme cross-sectional moves —
they're mean-reversion families. Family C bets *with* a peer's move:
if a peer makes a large USD-direction move at bar `t − k`, the target
may follow in the same USD-direction a few bars later. This is the
classic lead-lag idea applied to FX.

**Hypothesis:** when one major moves first on USD news, slower-moving
peers catch up. Following the peer's USD-aligned direction at a short
lag captures the catch-up move.

## Goals

- A new `lead_lag` mining family that consumes
  `build_cross_symbol_frame`.
- Per-peer mining: each peer trigger is a distinct candidate row so the
  audit can see which lead-lag pair (if any) carries edge.
- Each candidate scored against the random-entry baseline.

## Non-Goals

- No mean-reversion logic — that is families A and B.
- No multi-peer aggregation — the candidate is conditioned on a single
  named peer's lagged trigger. (A second sub-project could aggregate
  later if any individual pair clears baseline.)
- No clock resampling, no changes to existing families.

## Design

### 1. Trigger

For each (target, peer ≠ target, lag `k`, threshold `z*`):

- Read the peer's as-of-joined USD-aligned return at the target's bar
  `t − k` (column `xs_ret_z__{peer}` on the cross-symbol frame).
- If `xs_ret_z__{peer}[t − k] ≥ +z*`: peer moved USD-positive `k` bars
  ago → follow → `side_usd_aligned = +1`.
- If `xs_ret_z__{peer}[t − k] ≤ −z*`: peer moved USD-negative → follow
  → `side_usd_aligned = −1`.
- Otherwise no entry.

The raw-price side flips through the target's USD sign exactly as in
family B: `side_raw = side_usd_aligned * _USD_SIGN[target]`.

### 2. Param grid

`param_grid` yields `(horizon, peer, lag_k, trigger_z)`:

- `peer ∈ CROSS_SYMBOLS \ {target}` — 5 entries (resolved per-bar by
  the family, since the target isn't known at grid construction; the
  grid just yields `peer` strings, and the family filters out the
  self-trigger at runtime).
- `lag_k ∈ {1, 2}` — bars of lag.
- `trigger_z ∈ {1.5, 2.0}` — peer-σ threshold.
- horizons from `cfg["horizons"]`.

5 × 2 × 2 × horizons = 20 × horizons combos per regime. Reasonable
fan-out; smaller than the OCO sweep but larger than family B because the
"which peer" dimension is mined explicitly.

### 3. Outcome

`gross = side_raw * y_fwd_pips_h{horizon}[i]`. Same outcome contract as
the other directional-style families.

### 4. Family hooks

- `entry_indices(frame, regime_mask, params)` — builds the cross-symbol
  frame (cached), shifts the peer's `xs_ret_z__{peer}` column by `lag_k`
  bars (forward — the value at row `t − k` aligns with target row `t`),
  applies the `±trigger_z` threshold, and returns regime-masked entry
  indices.
- `measure_gross(frame, entries, params)` — looks up `side_raw` and
  multiplies by `y_fwd_pips_h{h}`.
- `candidate_metadata` — `family = "lead_lag"`;
  `state_id = "lead_lag__{regime}__p{peer}_k{lag}_z{trigger:.1f}"`;
  `regime_desc = "{regime};peer={peer};lag={lag};z={trigger:.1f}"`;
  `ml_ready_target_type = "lead_lag"`.

### 5. Look-ahead discipline

- The peer joins in `build_cross_symbol_frame` are backward as-of
  (PR #192 §6) — every `xs_ret_z__{peer}` at target row `t` is from a
  peer bar that closed `≤ t`.
- The lag shift moves the trigger value from row `t − k` (a strictly
  earlier target bar, whose peer value was already look-ahead-free)
  forward to row `t`. So the trigger at row `t` uses information from
  no later than the close of the peer bar at-or-before target bar
  `t − k`. Strictly past.

### 6. Self-peer filter

The param grid yields every peer regardless of target. At family
runtime, when the trigger peer matches the target symbol, the family
returns an empty entry array (no candidate row produced). This keeps
the grid declarative and avoids a per-target factory.

### 7. Output routing

A new file `{SYMBOL}_lead_lag_candidates.csv` per symbol. Not folded
into `dollar_residual` or `dispersion_rank` — the underlying mechanism
is fundamentally different (follow vs fade) and the per-peer state_id
needs its own file for legibility.

### 8. Caching

Reuses the cross-symbol frame cache pattern from families A and B. Per-
(frame_fingerprint, peer, lag_k) shifted-trigger arrays are also
memoised to avoid re-shifting per threshold sweep.

## Testing

- **Registration** — `lead_lag` satisfies `MiningFamily`; in
  `FAMILY_REGISTRY` and `_LIBRARY_TYPE_ALIASES["all"]`.
- **Self-peer is empty** — when `peer == target`, the family produces
  zero entries.
- **Sign mechanics** — on a fabricated frame where peer's USD-aligned
  return at `t − 1` is `+3σ`, the family produces a follow-direction
  entry at `t` (raw side = `+USD_SIGN[target]`).
- **No-op without context** — without `_dataset_dir` / `_horizons`
  injection (or with a non-cross-symbol target), the family returns
  empty arrays.
- **End-to-end smoke** — the 6-symbol synth fixture drives the family
  through to completion without error.

## File Map

- `scripts/mining_family.py` — `LeadLagFamily`; register it; alias
  entries.
- `scripts/run_tick_opportunity_mining.py` — output routing for the new
  CSV; library_type whitelist + `run()` return adjusted; main() writer.
- `tests/test_mining_family.py` — registration, sign mechanics, self-
  peer empty, no-op, end-to-end smoke.

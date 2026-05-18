# Double-Touch / Liquidity Sweep — `double_touch` Mining Family

**Date:** 2026-05-18
**Status:** Approved (design)
**Roadmap:** Sub-project 3 of `2026-05-18-microstructure-research-roadmap.md`

## Problem

OCO `first_touch` carries no edge — `p_up_first ≈ 0.50` in every regime, so
predicting which barrier is hit first is a coin flip. But the `oco_first_touch`
mining surfaced a second diagnostic: `both_window_rate` — the rate at which
*both* barriers are touched within the horizon — reaches 0.80 in some regimes.
Those regimes are where price pokes one side and then sweeps the other: a
stop-hunt / false-breakout.

This sub-project tests whether a *completed sweep* is informative. The edge, if
any, is not a prediction of which barrier is hit first — it is conditional on
the A→B sequence having already happened. After a false breakout up that
reverses down through a second level, does price *continue* down?

## Goals

- A new `double_touch` mining family that detects an A→B sweep and bets on
  continuation past B.
- Both sweep directions mined (up-then-down and down-then-up).
- Each candidate scored against the random-entry baseline (sub-project 0).

## Non-Goals

- No change to `oco_first_touch`, `oco_asymmetric`, the WFO, or the
  ml-dataset.
- No new gate thresholds — the random-entry baseline is the success bar.
- Not an OCO bracket family — it is not added to `ALLOWED_OCO_FAMILIES`, and
  the OCO family-allowlist contract is not broadened to cover it (see
  Governance).

## Design

### 1. `DoubleTouchFamily` — anchored two-stage sweep

A new `MiningFamily` registered as `double_touch`. Because its outcome is a
*signed forward return* rather than a barrier first-touch, it is structurally
a directional-style family — a sibling of `directional` and `directional_run`
— and its candidate rows fold into the `directional` output frame.

For a regime entry bar `i0` and a `sweep_dir ∈ {up, down}`:

1. **A-barrier** — placed `a_pips` from `i0`'s signal close in the `sweep_dir`
   direction. The frame is scanned forward up to `window_A` bars; the first
   bar that touches A is `tA`. No A-touch within `window_A` → no sweep, `i0`
   is dropped.
2. **B-barrier** — placed `b_pips` from the A-barrier price `pA` in the
   *opposite* direction (the reversal). The frame is scanned from `tA` forward
   up to `window_B` bars; the first bar that touches B is `tB`. No B-touch
   within `window_B` → no sweep, `i0` is dropped.
3. **Continuation bet** — from `tB`, over a continuation horizon `h2`:
   `gross = b_direction × forward return from tB`, where `b_direction` is
   opposite to `sweep_dir`. A completed up-sweep (A up, B down) bets short; a
   down-sweep bets long.

The asymmetry between "predict the first touch" (`oco_first_touch`, no edge)
and this family is the conditioning: `double_touch` does not predict the
sweep — it waits for a *completed* A→B sequence and asks the strictly
conditional question of whether continuation follows.

### 2. Touch and gross discipline

- A is touched when `high_ask ≥ A-price` (up sweep) or `low_bid ≤ A-price`
  (down sweep). `pA` is the **A-barrier price itself** — deterministic, not
  the bar's extreme — so B's placement does not depend on a sampled high/low.
- B is placed `b_pips` from `pA` in the opposite direction; touched against
  `high_ask` / `low_bid` symmetrically.
- Continuation gross uses the same bid/ask discipline as
  `_oco_precompute_candidates`: a short continuation (up-sweep) sells at
  `close_bid[tB]` and buys back at `close_ask[tB + h2]`; a long continuation
  does the reverse. Gross is therefore spread-aware, not a naive mid return.

### 3. New precompute engine

`_double_touch_precompute(frame, *, symbol, sweep_dir, a_pips, b_pips,
window_A, window_B, h2)` — a fully vectorised two-stage scan adapted from
`_oco_precompute_candidates`:

- Stage 1: loop `s ∈ 1..window_A`, recording the first A-touch step per `i0`.
- Stage 2: loop `s ∈ 1..window_B` from each `tA`, recording the first B-touch.
- Continuation: signed `h2`-bar return from each `tB`.

It returns the family-hook dict shape: `i0` (entry positions), `decided`
(bool mask — sweep completed), `gross` (continuation pips per `i0`), plus
diagnostics `t_a_step` and `t_b_step`. It is a new function;
`_oco_precompute_candidates` is not modified.

### 4. Family hooks

- `param_grid` — see §5.
- `entry_indices(frame, regime_mask, params)` — the `i0` bars where the sweep
  completed (`decided`) **and** `i0 ∈ regime_mask`.
- `measure_gross(frame, entries, params)` — maps any `i0` array to the
  precomputed continuation gross. `i0` values without a completed sweep map to
  `NaN`, so the random-entry baseline works unchanged: random `i0` draws that
  do not complete a sweep drop out, isolating the regime's contribution to
  sweep-continuation EV.
- `candidate_metadata` — `family = "double_touch"`;
  `state_id = "double_touch__{regime}__{sweep_dir}_a{a}_b{b}_wA{wA}_wB{wB}_h{h2}"`;
  `regime_desc` encodes the same; `ml_ready_target_type = "double_touch"`.

The family carries its own precompute cache (`_cache` keyed by
`_frame_fingerprint(frame)` + sorted params), matching the OCO families.

`CANDIDATE_SCHEMA_VERSION` stays `4.0` — candidate columns are unchanged;
`sweep_dir`, the pip sizes, the windows, and `h2` are encoded in `state_id` /
`regime_desc`.

### 5. Parameter grid

`param_grid` yields `(sweep_dir, a_pips, b_pips, window_A, window_B, h2)`:

- `sweep_dir ∈ {up, down}`
- `a_pips` — from `cfg["barrier_grid_pips"]` (reuses the existing knob)
- `b_pips ∈ {2.0, 4.0}`
- `window_A ∈ {5, 15}` bars
- `window_B ∈ {5, 15}` bars
- `h2` — from `cfg["horizons"]`

With a 2-value `barrier_grid_pips` that is `2 × 2 × 2 × 2 × 2 × |horizons|`
≈ 192 combos per regime — comparable to `oco_asymmetric`'s 144.

### 6. Output wiring

- `resolve_families` gains the alias `"double_touch": ["double_touch"]`.
- In `run()`, `double_touch` joins the `{directional, directional_run}`
  branch — its rows fold into the `directional` output frame.
- In `_mine_frame_pair`, `double_touch` joins the directional `selection_pass`
  branch (the annualized-fills gate) and skips the `oco_first_touch`-only
  `both_window_rate` / `p_up_first` precompute block.

### 7. Governance

`double_touch` is intentionally **not** `oco_`-prefixed. `ALLOWED_OCO_FAMILIES`
in `tests/test_oco_candidate_family_allowlist.py` governs symmetric and
asymmetric OCO *bracket* families; `double_touch` is a directional-output
family triggered by a touch sequence, so it is outside that allowlist and the
allowlist contract is not broadened to cover it.

The family's look-ahead audit is this section: entry conditioning is
**regime-only** on `i0`; `tA`, `tB`, and the continuation window are all
strictly forward of `i0`; no outcome-derived quantity filters the candidate
universe. The construction is look-ahead-free by the same contract as the
symmetric engine.

## Data Flow

```
velocity parquet
  → run(): resolve_families includes "double_touch" when requested
  → _mine_frame_pair: for each (sweep_dir, a, b, wA, wB, h2) × regime
      entry_indices (regime i0 with completed sweep)
      → measure_gross (signed continuation return from tB)
      → candidate row + random_entry_baseline
  → directional candidate frame (family == "double_touch")
```

## Error Handling

- A non-positive `a_pips` / `b_pips` / `window_A` / `window_B` / `h2` →
  `ValueError` at `param_grid` time.
- A frame too short for `window_A + window_B + h2` → empty `i0`, handled
  exactly as the symmetric engine handles a too-short frame.
- An `i0` that touches A but never touches B within `window_B` → `decided`
  False, dropped from `entry_indices`.
- A `tB` whose continuation window runs off the end of the frame → `gross`
  `NaN` for that `i0`, dropped by the finite-gross filter.
- Random-baseline degenerate cases inherit sub-project 0's `NaN` behaviour.

## Testing

- **Precompute correctness** — on a hand-built frame with a known A→B sweep,
  `_double_touch_precompute` recovers the expected `t_a_step`, `t_b_step`, and
  gross sign.
- **No-sweep cases** — frames where A is never touched, or where B is never
  touched within `window_B`, yield `decided = False` for those `i0`.
- **Bet direction** — a completed up-sweep produces short-continuation gross
  (negative when price keeps rising after `tB`, positive when it falls); the
  sign is verified against a constructed continuation move.
- **No false edge** — on a driftless synthetic frame, sweep candidates' gross
  EV sits within the random-entry baseline noise band (`z` NaN or `< 2.0`).
- **Detects structure** — on a synthetic frame with injected post-sweep
  continuation in one regime, that regime's candidates score `z > 2.0`.
- **Registry conformance** — `double_touch` satisfies the `MiningFamily`
  protocol; `resolve_families("double_touch")` returns `["double_touch"]`.
- **End-to-end** — `run()` with `library_type = "double_touch"` produces a
  non-empty directional frame whose rows all have `family == "double_touch"`
  and carry the `random_baseline_*` columns.

## Success Criterion

A candidate is real only if its gross EV beats the random-entry baseline
(roadmap shared criterion). The mining audit reports, per regime and sweep
direction, whether post-sweep continuation clears the baseline — the result
that decides whether liquidity-sweep conditioning is worth carrying forward
into sub-project 4.

## File Map

- `scripts/mining_family.py` — add `DoubleTouchFamily` (with `_cache` /
  `clear_cache`); register it in `FAMILY_REGISTRY`; add the `double_touch`
  alias to `_LIBRARY_TYPE_ALIASES`.
- `scripts/run_tick_opportunity_mining.py` — add `_double_touch_precompute`;
  extend the `run()` family-merge branch and the `_mine_frame_pair`
  `selection_pass` branch to include `double_touch`.
- `tests/test_mining_family.py` — `double_touch` conformance, hook behaviour,
  bet-direction, no-sweep cases.
- `tests/test_tick_opportunity_mining.py` — precompute correctness,
  end-to-end mining, no-false-edge and structure-detection statistical tests.

# Pullback Continuation — `pullback` Mining Family

**Date:** 2026-05-18
**Status:** Approved (design)
**Roadmap:** Sub-project 4 of `2026-05-18-microstructure-research-roadmap.md`

## Problem

OCO `first_touch` carries no edge — `p_up_first ≈ 0.50` in every regime, so
predicting which barrier is hit first is a coin flip. Sub-project 3
(`double_touch`) tested whether a *completed sweep* is informative. This
sub-project tests a different conditional sequence: a directional **impulse**,
a partial **pullback** against it, and then a **resumption** back to the
impulse extreme.

The edge, if any, is not a prediction — it is conditional on a completed
impulse → pullback → resumption sequence having already happened. After price
drives `M` pips, retraces a fraction `R` of that move, and then pushes back to
the impulse extreme, does it *continue* in the original direction?

## Goals

- A new `pullback` mining family that detects an impulse → pullback →
  resumption sequence and bets on continuation past the resumption point.
- Both impulse directions mined (up-impulse and down-impulse).
- Each candidate scored against the random-entry baseline (sub-project 0).

## Non-Goals

- No change to `oco_first_touch`, `directional`, `double_touch`, the WFO, or
  the ml-dataset.
- No new gate thresholds — the random-entry baseline is the success bar.
- Not an OCO bracket family — it is not added to `ALLOWED_OCO_FAMILIES`, and
  the OCO family-allowlist contract is not broadened to cover it (see
  Governance).

## Design

### 1. `PullbackFamily` — anchored four-stage engine

A new `MiningFamily` registered as `pullback`. Because its outcome is a
*signed forward return* rather than a barrier first-touch, it is structurally
a directional-style family — a sibling of `directional` and `double_touch` —
and its candidate rows fold into the `directional` output frame.

For a regime entry bar `i0` and an `impulse_dir ∈ {up, down}`:

1. **Impulse** — an impulse barrier is placed `M` pips from `i0`'s signal
   close in the `impulse_dir` direction. The frame is scanned forward up to
   `w_I` bars; the first bar that touches it is `tI`. No touch within `w_I` →
   no setup, `i0` is dropped. The impulse extreme price `pI` is the **barrier
   price itself** — deterministic, not a sampled bar extreme.
2. **Pullback** — a pullback barrier is placed `R × M` pips from `pI` in the
   *opposite* direction (the retracement). The frame is scanned from `tI`
   forward up to `w_P` bars; the first bar that touches it is `tP`. No touch
   within `w_P` → no setup, `i0` is dropped.
3. **Resumption** — a resumption barrier is placed back at `pI` (the impulse
   extreme itself). The frame is scanned from `tP` forward up to `w_R` bars;
   the first bar that touches `pI` is `tR`. No touch within `w_R` → setup
   incomplete, `i0` is dropped (`decided` False).
4. **Continuation bet** — from `tR`, over a continuation horizon `h`:
   `gross = impulse_direction × forward return from tR`. A completed
   up-impulse setup bets long; a down-impulse setup bets short.

The asymmetry between "predict the first touch" (`oco_first_touch`, no edge)
and this family is the conditioning: `pullback` does not predict the move — it
waits for a *completed* impulse → pullback → resumption sequence and asks the
strictly conditional question of whether continuation follows.

### 2. Touch and gross discipline

- An up-direction barrier is touched when `high_ask ≥ barrier-price`; a
  down-direction barrier when `low_bid ≤ barrier-price`. Applied symmetrically
  per stage and per `impulse_dir`.
- The impulse extreme `pI` is the **impulse barrier price itself** —
  deterministic — so the pullback and resumption barriers do not depend on a
  sampled high/low.
- The pullback barrier is `R × M` pips from `pI` opposite the impulse; the
  resumption barrier is `pI` exactly. "Resumption *past* the extreme" is then
  captured by the continuation gross, not by an extra offset.
- Signal close is `close_ask[i0]` for an up-impulse, `close_bid[i0]` for a
  down-impulse (matches `double_touch`).
- Continuation gross uses the same bid/ask discipline as
  `_double_touch_precompute`: a long continuation (up-impulse) buys at
  `close_ask[tR]` and sells at `close_bid[tR + h]`; a short continuation does
  the reverse. Gross is therefore spread-aware, not a naive mid return.

### 3. New precompute engine

`_pullback_precompute(frame, *, symbol, impulse_dir, m_pips, r_frac,
window_I, window_P, window_R, h)` — a fully vectorised four-stage scan
adapted from `_double_touch_precompute`:

- Stage 1: loop `s ∈ 1..window_I`, recording the first impulse-touch step per
  `i0`.
- Stage 2: loop `s ∈ 1..window_P` from each `tI`, recording the first
  pullback-touch.
- Stage 3: loop `s ∈ 1..window_R` from each `tP`, recording the first
  resumption-touch.
- Continuation: signed `h`-bar return from each `tR`.

It returns the family-hook dict shape: `i0` (entry positions), `decided`
(bool mask — all three stages completed), `gross` (continuation pips per
`i0`), plus diagnostics `t_i_step`, `t_p_step`, `t_r_step`. It is a new
function; `_double_touch_precompute` is not modified.

### 4. Family hooks

- `param_grid` — see §5.
- `entry_indices(frame, regime_mask, params)` — the `i0` bars where the
  sequence completed (`decided`) **and** `i0 ∈ regime_mask`.
- `measure_gross(frame, entries, params)` — maps any `i0` array to the
  precomputed continuation gross. `i0` values without a completed sequence map
  to `NaN`, so the random-entry baseline works unchanged: random `i0` draws
  that do not complete a setup drop out, isolating the regime's contribution
  to pullback-continuation EV.
- `candidate_metadata` — `family = "pullback"`;
  `state_id = "pullback__{regime}__{impulse_dir}_M{M}_R{R}_wI{wI}_wP{wP}_wR{wR}_h{h}"`;
  `regime_desc` encodes the same; `ml_ready_target_type = "pullback"`.

The family carries its own precompute cache (`_cache` keyed by
`_frame_fingerprint(frame)` + sorted params, with a `clear_cache()` method),
matching `double_touch` and the OCO families.

`CANDIDATE_SCHEMA_VERSION` stays `4.0` — candidate columns are unchanged;
`impulse_dir`, `M`, `R`, the windows, and `h` are encoded in `state_id` /
`regime_desc`.

### 5. Parameter grid

`param_grid` yields `(impulse_dir, m_pips, r_frac, window_I, window_P, h)`;
`window_R` is fixed:

- `impulse_dir ∈ {up, down}`
- `m_pips` — from `cfg["barrier_grid_pips"]` (reuses the existing knob)
- `r_frac ∈ {0.382, 0.5, 0.618}`
- `window_I ∈ {5, 15}` bars
- `window_P ∈ {5, 15}` bars
- `window_R = 10` bars (fixed — a completed pullback resumes quickly or not at
  all)
- `h` — from `cfg["horizons"]`

With a 2-value `barrier_grid_pips` that is `2 × 2 × 3 × 2 × 2 × |horizons|`
= `48 × |horizons|` combos per regime — ~144 with a 3-value `horizons`, in
line with `double_touch` (~192) and `oco_asymmetric` (~144).

### 6. Output wiring

- `resolve_families` gains the alias `"pullback": ["pullback"]`.
- `run()` accepts `library_type = "pullback"`; `pullback` joins the
  directional family-merge branch — its rows fold into the `directional`
  output frame.
- In `_mine_frame_pair`, `pullback` joins the directional `selection_pass`
  branch (the annualized-fills gate) and skips the `oco_first_touch`-only
  `both_window_rate` / `p_up_first` precompute block.

### 7. Governance

`pullback` is intentionally **not** `oco_`-prefixed. `ALLOWED_OCO_FAMILIES`
in `tests/test_oco_candidate_family_allowlist.py` governs symmetric and
asymmetric OCO *bracket* families; `pullback` is a directional-output family
triggered by a price sequence, so it is outside that allowlist and the
allowlist contract is not broadened to cover it.

The family's look-ahead audit is this section: entry conditioning is
**regime-only** on `i0`; `tI`, `tP`, `tR`, and the continuation window are all
strictly forward of `i0`; no outcome-derived quantity filters the candidate
universe. The construction is look-ahead-free by the same contract as the
`double_touch` engine.

## Data Flow

```
velocity parquet
  → run(): resolve_families includes "pullback" when requested
  → _mine_frame_pair: for each (impulse_dir, M, R, wI, wP, h) × regime
      entry_indices (regime i0 with completed impulse→pullback→resumption)
      → measure_gross (signed continuation return from tR)
      → candidate row + random_entry_baseline
  → directional candidate frame (family == "pullback")
```

## Error Handling

- A non-positive `m_pips` / `window_I` / `window_P` / `h`, or an `r_frac`
  outside `(0, 1)` → `ValueError` at `param_grid` time.
- A frame too short for `window_I + window_P + window_R + h` → empty `i0`,
  handled exactly as `_double_touch_precompute` handles a too-short frame.
- An `i0` that touches the impulse but never the pullback within `window_P`,
  or the pullback but never the resumption within `window_R` → `decided`
  False, dropped from `entry_indices`.
- A `tR` whose continuation window runs off the end of the frame → `gross`
  `NaN` for that `i0`, dropped by the finite-gross filter.
- Random-baseline degenerate cases inherit sub-project 0's `NaN` behaviour.

## Testing

- **Precompute correctness** — on a hand-built frame with a known
  impulse → pullback → resumption sequence, `_pullback_precompute` recovers
  the expected `t_i_step`, `t_p_step`, `t_r_step`, and gross sign.
- **No-completion cases** — frames where the impulse, the pullback, or the
  resumption never completes within its window yield `decided = False` for
  those `i0`.
- **Bet direction** — a completed up-impulse setup produces long-continuation
  gross (positive when price keeps rising after `tR`, negative when it
  falls); the sign is verified against a constructed continuation move.
- **No false edge** — on a driftless synthetic frame, pullback candidates'
  gross EV sits within the random-entry baseline noise band (`z` NaN or
  `< 2.0`).
- **Detects structure** — on a synthetic frame with injected
  post-resumption continuation in one regime, that regime's candidates score
  `z > 2.0`.
- **Registry conformance** — `pullback` satisfies the `MiningFamily`
  protocol; `resolve_families("pullback")` returns `["pullback"]`.
- **End-to-end** — `run()` with `library_type = "pullback"` produces a
  non-empty directional frame whose rows all have `family == "pullback"` and
  carry the `random_baseline_*` columns.

## Success Criterion

A candidate is real only if its gross EV beats the random-entry baseline
(roadmap shared criterion). The mining audit reports, per regime and impulse
direction, whether post-resumption continuation clears the baseline — the
result that decides whether pullback conditioning is worth carrying forward
into sub-project 5.

## File Map

- `scripts/mining_family.py` — add `PullbackFamily` (with `_cache` /
  `clear_cache`); register it in `FAMILY_REGISTRY`; add the `pullback` alias
  to `_LIBRARY_TYPE_ALIASES`.
- `scripts/run_tick_opportunity_mining.py` — add `_pullback_precompute`;
  extend the `run()` family-merge branch and the `_mine_frame_pair`
  `selection_pass` branch to include `pullback`.
- `tests/test_mining_family.py` — `pullback` conformance, hook behaviour,
  bet-direction, no-completion cases.
- `tests/test_tick_opportunity_mining.py` — precompute correctness,
  end-to-end mining, no-false-edge and structure-detection statistical tests.

# Consecutive-Move Persistence — `directional_run` Mining Family

**Date:** 2026-05-18
**Status:** Approved (design)
**Roadmap:** Sub-project 2 of `2026-05-18-microstructure-research-roadmap.md`

## Problem

The `directional` mining family scored AUC ≈ 0.50 across all six symbols —
single-bar tick-bar direction is unpredictable. That is an *unconditional*
result. It does not test whether direction becomes predictable *given* a
streak of consecutive same-sign bars. Momentum (streaks continue) and
exhaustion (streaks revert) are real microstructure effects a per-bar
classifier averages away.

This sub-project is a cheap falsification check: condition entry on
consecutive-run length and measure whether the next move is biased. If
nothing beats the random-entry baseline, that is a clean, fast negative.

## Goals

- A new `directional_run` mining family triggered by consecutive-run length.
- Both continuation and reversion bets mined for every run bucket.
- Each candidate scored against the random-entry baseline (sub-project 0).

## Non-Goals

- No barriers — outcome is a signed forward return, not a first-touch.
- No change to the `directional` family, the WFO, or the ml-dataset.
- No new gate thresholds — the random-entry baseline is the success bar.

## Design

### 1. `DirectionalRunFamily` — streak-triggered directional bet

A new `MiningFamily` registered as `directional_run`. It is a directional
family — a structural sibling of `directional` — but entry is triggered by
streak length rather than a regime family-state.

- **Run definition** — for bar `i`, the consecutive-run length is the count
  of immediately-preceding bars (including `i`) sharing the same sign of
  `ret1_pips` (the per-bar return already on the frame). A companion run-sign
  (±1) records the streak direction. Both come from a vectorised module
  helper `_run_length(frame) -> (run_len, run_sign)`. The family hooks call
  it directly — it is cheap, mutates nothing, and needs no plumbing into
  `_mine_frame_pair`.
- **Entry** — bars whose run length falls in the candidate's bucket,
  intersected with the regime mask supplied by the mining loop. A candidate
  is therefore `(regime, run-bucket, bet, horizon)`.
- **Outcome** — for a **continuation** bet, `side = run_sign` (ride the
  streak); for a **reversion** bet, `side = -run_sign` (fade it). Gross pips
  `= side * y_fwd_pips_h{h}`. Both bets are mined for every bucket; the
  random-entry baseline reveals which, if either, carries edge.

The `directional` AUC ≈ 0.50 result says single-bar direction is
unpredictable. This family asks the strictly conditional question — given a
streak of N same-sign bars, is the next move biased?

### 2. Parameter grid

`param_grid` yields `(horizon, run_bucket, bet)`:

- `run_bucket ∈ {"2", "3", "4", "5", "6+"}` — exact run length 2/3/4/5, plus
  a tail bucket for run length ≥ 6.
- `bet ∈ {"continuation", "reversion"}`
- horizons from `cfg["horizons"]`

5 buckets × 2 bets × 6 horizons = 60 combos per regime.

### 3. Family hooks

- `entry_indices(frame, regime_mask, params)` — bars where `_run_len` matches
  the bucket (exact for 2-5, `>= 6` for the tail), intersected with
  `regime_mask`.
- `measure_gross(frame, entries, params)` — `side = run_sign` for
  continuation, `-run_sign` for reversion; returns
  `side[entries] * y_fwd_pips_h{h}[entries]`. Accepts any entry index array,
  so the random-entry baseline works unchanged.
- `candidate_metadata` — `family = "directional_run"`;
  `state_id = "directional_run__{regime}__n{bucket}_{bet}"`;
  `regime_desc = "{regime};run={bucket};bet={bet}"`;
  `ml_ready_target_type = "directional_run"`.

`CANDIDATE_SCHEMA_VERSION` stays `4.0` — candidate columns are unchanged; the
run bucket and bet are encoded in `state_id` / `regime_desc`.

### 4. Governance

`directional_run` is a directional family, not an OCO family — the OCO
family-allowlist contract test does not apply, and `ALLOWED_OCO_FAMILIES` is
not changed. `resolve_families` gains wiring so `directional_run` can be
mined (a new `library_type` value or an explicit `cfg["families"]` list —
the plan picks the least-invasive option).

## Data Flow

```
velocity parquet
  → run(): resolve_families includes "directional_run" when requested
  → _mine_frame_pair: for each (run_bucket, bet, horizon) × regime
      entry_indices (run-length bars) → measure_gross (signed forward return)
      → candidate row + random_entry_baseline
  → {symbol}_directional_run_candidates.csv
```

## Error Handling

- An unknown `run_bucket` or `bet` value → `ValueError` at `param_grid` /
  hook time.
- A frame too short for the horizon → trailing bars excluded from
  `entry_indices` (same `valid[-h:] = False` rule as the `directional`
  family).
- Random-baseline degenerate cases inherit sub-project 0's `NaN` behaviour.

## Testing

- **`_run_length`:** on a hand-built sign sequence `+ + + - - +`, the helper
  returns `run_len = [1,2,3,1,2,1]` and `run_sign = [+,+,+,-,-,+]`.
- **Bucketing:** a frame with known run lengths yields the right entry counts
  for buckets `2`-`5` and `6+`; exact buckets are disjoint and `6+` captures
  the tail.
- **Bet symmetry:** continuation and reversion gross are exact negatives of
  each other for the same entries.
- **No false edge:** on a driftless synthetic frame, both bets sit within the
  random-entry baseline noise band (small `|z|`).
- **Detects structure:** on a synthetic frame with injected momentum (streaks
  tend to continue), continuation candidates score `z > 0` and reversion
  `z < 0`.
- **Registry conformance:** `directional_run` satisfies the `MiningFamily`
  protocol.

## Success Criterion

A candidate is real only if its gross EV beats the random-entry baseline
(roadmap shared criterion). The mining audit reports, per regime and run
bucket, whether continuation or reversion clears the baseline — the result
that decides whether streak conditioning is worth carrying forward.

## File Map

- `scripts/mining_family.py` — add `DirectionalRunFamily`; register it.
- `scripts/run_tick_opportunity_mining.py` — add `_run_length` helper;
  extend `resolve_families` wiring.
- `tests/test_mining_family.py` — `directional_run` conformance, `_run_length`
  unit tests, bucketing, bet symmetry.
- `tests/test_tick_opportunity_mining.py` — no-false-edge and
  structure-detection tests.

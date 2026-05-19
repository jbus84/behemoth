# No-touch / Sell-the-Range — `no_touch` Mining Family

**Date:** 2026-05-19
**Status:** Approved (design)
**Roadmap:** Sub-project 5 of `2026-05-18-microstructure-research-roadmap.md`

## Problem

OCO `first_touch` carries no edge — `p_up_first ≈ 0.50` in every regime, so
predicting which barrier is hit first is a coin flip. Sub-projects 3
(`double_touch`) and 4 (`pullback`) tested conditional *sequences*. This
sub-project tests the honest *inverse* of first-touch: profit when **neither**
barrier is touched within the horizon — a range-bound bet.

First-touch direction is a coin flip, but the no-touch rate is not: the
fraction of bars where a horizon completes without touching either `±K`
barrier varies across regimes (`both_window_rate` reaches 0.80 in some
regimes, near 0 in others). If that variation is real and exploitable, a
range-fade placed in low-touch regimes will beat a random-entry baseline.

## Goals

- A new `no_touch` mining family that places a symmetric `±K` range-fade bet
  at every regime bar and scores it as a capped-win / variable-loss payoff.
- Each candidate scored against the random-entry baseline (sub-project 0).

## Non-Goals

- No change to `oco_first_touch`, `directional`, `double_touch`, `pullback`,
  the WFO, or the ml-dataset's existing target types.
- No new gate thresholds — the random-entry baseline is the success bar.
- Not an OCO bracket family — `no_touch` is **not** added to
  `ALLOWED_OCO_FAMILIES`, and the OCO family-allowlist contract is not
  broadened to cover it (see Governance). It reuses the OCO *precompute*, but
  it is a range-fade payoff bet, not a TP/SL bracket.
- No asymmetric barriers — barriers are symmetric `±K`. Asymmetric payoff is
  sub-project 1's territory.

## Design

### 1. The bet — capped win, variable loss

For a regime entry bar `i0`, a symmetric range-fade is placed: barriers at
`+K` and `-K` pips from `i0`'s signal close, `K` drawn from
`barrier_grid_pips`.

- **No touch** — neither barrier is touched within `h` bars. The range held;
  the bet wins a fixed `gross = +K` pips.
- **Touch** — a barrier is first touched at bar `tT`. The bet loses: it is
  scored by the breakout continuation `h` bars past the touch. The loss is
  `gross = -(oco_gross)`, where `oco_gross` is the signed touch→touch+h
  continuation P&L (defined in §3). A breakout that keeps running books a
  larger loss; one that retraces books a partial recovery (small loss, or a
  small positive).

The payoff is therefore a capped win (`+K`) with a variable, path-dependent
loss — the honest inverse of first-touch: first-touch *predicts* a barrier;
`no_touch` profits from *neither* being reached.

### 2. Entry universe — every regime bar

Unlike `oco_first_touch`, `double_touch`, and `pullback` — which gate entries
on a completed setup (`decided`) — the `no_touch` family does **not** gate on
`decided`. A range-fade is placed unconditionally at every valid regime bar;
un-touched bars are the *wins*, not dropped candidates. `entry_indices`
returns every valid regime `i0`.

"Valid" means `i0` lies within the precompute's effective range — the OCO
precompute's `n_eff = len(frame) - 2*h` already reserves room for the
worst-case touch (`tT ≤ i0 + h`) plus the continuation horizon (`tT + h`), so
every `i0` it returns is in-bounds for both legs.

### 3. Engine — reuse `_oco_precompute_candidates`

`no_touch` adds **no new precompute engine**. It reuses
`_oco_precompute_candidates(frame, symbol, horizon, barrier_pips)`, whose
output already provides everything needed:

- `i0` — signal bar indices (decision-time).
- `decided` — True when a barrier was touched within `h` (decision-time).
- `gross` — the signed continuation P&L: enter at the first-touch bar's
  close, hold `h` bars, signed by the first-touch side. This is OCO's
  existing "enter-at-touch, hold-h-bars" P&L; for `no_touch` it is the
  breakout continuation past the touched barrier.

The `no_touch` gross is a re-interpretation of that output:

```
no_touch_gross = where(decided, -oco_gross, +K)
```

- `decided` False (no touch) → `+K`.
- `decided` True (touch) → `-(oco_gross)`. OCO's `gross` is signed by the
  first-touch side, so an up-touch that continues up is `oco_gross > 0`;
  negated, the range-seller's loss is correctly negative.
- `decided` True but `oco_gross` is NaN (continuation exit out of bounds) →
  stays NaN. Same convention as `double_touch` / `pullback`; downstream
  nan-filters handle it.

**Documented approximation:** OCO's continuation enters at the *touch bar's
close*, not the exact `±K` barrier price. The two differ by sub-pip overshoot
plus spread. This is accepted: the difference is immaterial against the
random-entry baseline (which is scored on the identical construction), and
reusing the most-tested touch-scan in the module is worth more than exact
barrier-price precision. A dedicated `_no_touch_precompute` measuring from the
exact barrier price is a possible future refinement, not part of this design.

### 4. `NoTouchFamily` — `MiningFamily` protocol

A new `MiningFamily` registered as `no_touch` in `FAMILY_REGISTRY`, with the
`"no_touch": ["no_touch"]` alias added to `_LIBRARY_TYPE_ALIASES`.

- `param_grid(cfg)` — the cross product of `barrier_grid_pips` (`K`) and
  `horizons` (`h`). Symmetric barriers, so no direction axis. Rejects
  non-positive `K` or `h` with `ValueError`, matching the sibling families.
- `_precompute(frame, symbol, params)` — calls `_oco_precompute_candidates`;
  per-frame cache keyed by `(_frame_fingerprint(frame), sorted params)`,
  mirroring `DoubleTouchFamily`. `clear_cache()` provided for long-lived
  processes. `ValueError` from the engine → cached `None`.
- `entry_indices(frame, regime_mask, params)` — every `prep["i0"]` whose bar
  is in `regime_mask`; **not** gated on `decided`.
- `measure_gross(frame, entries, params)` — maps an arbitrary entry array to
  `no_touch_gross` via `pd.Series(...).reindex(entries)`, so it serves both
  real entries and random-baseline draws. Entries outside the precompute
  universe map to NaN.
- `candidate_metadata(regime_name, params)` — `family='no_touch'`;
  `state_id = f"no_touch__{regime}__K{k:g}_h{h}"`;
  `regime_desc` includes `K` and `h`;
  `ml_ready_target_type='no_touch'`.

### 5. Wiring — `run()` returns a fourth frame

`no_touch` candidate rows are a payoff bet — neither a signed directional
return nor a first-touch outcome — so they land in a dedicated frame rather
than folding into `directional` or `oco`.

- `run()` `library_type` validation accepts `no_touch`.
- `run()` returns a **4-tuple**: `(directional, oco, no_touch, summary)`.
- `_mine_frame_pair` — `no_touch` is added to the annualized-count branch
  (`fam_name in (...)`) and the `selection_pass` gating branch, alongside
  `directional` / `double_touch` / `pullback`.
- `_build_summary(directional, oco, no_touch)` — extended to fold `no_touch`
  counts into the summary.
- `_save_report(...)` — extended to take and report the `no_touch` frame.
- `main()` — unpacks the 4-tuple and writes
  `{SYMBOL}_no_touch_candidates.csv` alongside the directional / oco / summary
  CSVs.

**Callers updated** (the 8 sites that unpack `run()`):

- `scripts/run_tick_opportunity_mining.py` `main()` block.
- `scripts/build_tick_opportunity_ml_dataset.py:882` — `no_touch` unused there
  (Non-Goal: no ml-dataset change).
- `tests/test_tick_opportunity_ml_dataset.py:126`.
- `tests/test_tick_opportunity_mining.py` — five unpack sites (204, 534, 565,
  657, 741).

No-arg `run(cfg)` callers (`select_directional_rolling.py`,
`select_oco_reduced_core*.py`, `verify_oco_tick_exact_shortlist.py`,
`test_tick_opportunity_ml_dataset.py:202`) discard the return value and need
no change.

### 6. Look-ahead discipline

Entry conditioning is `i0` only. The touch scan, the first-touch bar `tT`,
and the continuation window `tT..tT+h` are all strictly forward of `i0`.
`regime_mask` is applied at `i0`. The `no_touch` family inherits the OCO
precompute's existing look-ahead-free guarantees unchanged — it only
re-labels outputs, it does not change which bars are read.

## Governance

`data/analysis/tick_opportunity_mining/` is governance-locked truth; this
sub-project adds a new family and does not regenerate locked artifacts. The
OCO family-allowlist contract (`tests/test_oco_candidate_family_allowlist.py`)
is **not** broadened — a test asserts `no_touch` is absent from
`ALLOWED_OCO_FAMILIES`, mirroring the `pullback` precedent.

## Testing

- **Precompute reuse** — a deterministic range-bound builder (price oscillates
  inside `±K`, never touches → all candidates `decided=False`, `gross=+K`) and
  a trending builder (price runs through a barrier → `decided=True`, negative
  `gross`).
- **Family conformance** — `no_touch` registered, resolves, satisfies the
  `MiningFamily` protocol; `param_grid` count equals `len(K) × len(h)`;
  `candidate_metadata` shape and `state_id` format.
- **Hooks** — `entry_indices` returns *all* regime bars (not gated on
  `decided`); `measure_gross` maps arbitrary entry arrays and yields `+K` for
  un-touched and negative for touched-and-continuing.
- **Governance** — `no_touch` absent from the OCO allowlist contract.
- **End-to-end** — `test_run_mines_no_touch`: `run()` with
  `library_type='no_touch'` returns a populated 4-tuple.
- **Statistical** — no-false-edge on driftless data (`z < 2.0` vs the
  random-entry baseline) and detects-structure on a constructed range-bound
  regime (`z > 2.0`), both without tuning.

## File Structure

- `scripts/mining_family.py` — add `NoTouchFamily`; register in
  `FAMILY_REGISTRY`; add the `no_touch` alias to `_LIBRARY_TYPE_ALIASES`.
- `scripts/run_tick_opportunity_mining.py` — extend `run()` (`library_type`
  check, 4-tuple return), `_mine_frame_pair` (annualized-count +
  `selection_pass` branches), `_build_summary`, `_save_report`, and `main()`.
- `scripts/build_tick_opportunity_ml_dataset.py` — update the `run()` unpack.
- `tests/test_mining_family.py` — `no_touch` conformance, grid, metadata,
  hook, and statistical tests.
- `tests/test_tick_opportunity_mining.py` — range-bound + trending builders;
  precompute-reuse tests; end-to-end `test_run_mines_no_touch`; update the
  existing 4-tuple unpack.
- `tests/test_tick_opportunity_ml_dataset.py` — update the `run()` unpack.
- `docs/superpowers/specs/2026-05-18-microstructure-research-roadmap.md` —
  update the status table row 5 to `Specced`.

# Asymmetric Barriers — `oco_asymmetric` Mining Family

**Date:** 2026-05-18
**Status:** Approved (design)
**Roadmap:** Sub-project 1 of `2026-05-18-microstructure-research-roadmap.md`

## Problem

OCO `first_touch` mining has no edge: `p_up_first ≈ 0.50` in every regime,
0 of 4,080 candidates positive on both train and test. First-touch direction
is a coin flip, so symmetric brackets cannot extract value.

Asymmetric barriers — an up-barrier and a down-barrier at *different*
distances — are the cheapest research direction to test next. They reuse the
existing OCO mining path and ask a sharper question: does any *regime* bend
the barrier-touch probabilities away from the driftless-walk rate enough that
an asymmetric bracket turns gross-positive?

## Goals

- A new `oco_asymmetric` mining family with an independently-sized up-barrier
  and down-barrier.
- Each candidate scored against the random-entry baseline (sub-project 0).
- `oco_first_touch` and its precompute left untouched.

## Non-Goals

- No directional side selection — entry is regime-conditioned, not
  side-picked (see Design §1).
- No change to `oco_first_touch`, `_oco_precompute_candidates`, the WFO, or
  the ml-dataset.
- No new gate thresholds — the random-entry baseline is the success bar.

## Design

### 1. `OcoAsymmetricFamily` — non-directional, asymmetric bracket

A new `MiningFamily` registered as `oco_asymmetric`. It mirrors
`OcoFirstTouchFamily` structurally:

- **Entry** — regime-conditioned bars (`_regime_masks`), non-directional. No
  side is chosen at entry.
- **Outcome** — first touch of an asymmetric bracket: gross pips is
  `+up_pips` if the up-barrier is touched first, `−down_pips` if the
  down-barrier is touched first, else the horizon-exit P&L.

The asymmetry itself is the directional expression: a regime that drifts up
is captured by a wide up-barrier and a tight down-barrier. The family does
not pick long/short; it lets the barrier sizing express the view.

**Why this can have edge when `oco_first_touch` did not:** for a driftless
random walk, asymmetric brackets still have gross EV ≈ 0 — P(up touched
first) = down/(up+down) exactly cancels the payoff. Asymmetry alone is *not*
an edge. The family tests whether a *regime* bends the touch probabilities
off that martingale rate. The random-entry baseline (same barriers, random
entry bars) isolates that regime contribution.

### 2. Parameter grid — stop + reward ratio

`param_grid` yields `(horizon, down_pips, rr)` with `up_pips = down_pips × rr`:

- `down_pips ∈ {2, 3, 5, 8}`
- `rr ∈ {0.5, 0.75, 1.0, 1.5, 2.0, 3.0}`
- horizons from `cfg["horizons"]`

24 barrier combos × 6 horizons = 144 per regime. `rr = 1.0` is the symmetric
control *inside* the family — it lets the audit compare each regime's
asymmetric candidates against its own symmetric baseline, independently of
the random-entry baseline.

### 3. Asymmetric touch engine

`_oco_asymmetric_precompute(frame, *, symbol, horizon, up_pips, down_pips)`
returns the same dict shape the family hooks consume from
`_oco_precompute_candidates` — `i0` (entry positions), `decided` (bool mask
over `i0`), `gross` (gross pips per `i0`), and `both_touched_lookahead` (a
diagnostic, not used for selection). The up-barrier and down-barrier are
placed in price terms from each entry bar's signal close; first touch is
resolved bar-by-bar against bid/ask highs and lows, look-ahead-free — the
same touch contract as the symmetric engine.

It is a new function adapted from `_oco_precompute_candidates`;
`_oco_precompute_candidates` itself is not modified.

### 4. Candidate metadata

`family = "oco_asymmetric"`;
`state_id = "oco_asymmetric__{regime}__d{down}_rr{rr}"`;
`regime_desc = "{regime};down={down};rr={rr}"`;
`ml_ready_target_type = "oco_asymmetric"`.

`CANDIDATE_SCHEMA_VERSION` stays `4.0` — the candidate columns are unchanged;
`down_pips` and `rr` are encoded in `state_id`/`regime_desc`, exactly as the
symmetric family encodes `barrier`.

### 5. Governance — family allowlist

`ALLOWED_OCO_FAMILIES` in `tests/test_oco_candidate_family_allowlist.py`
gains `"oco_asymmetric"`. Adding it is a deliberate audit step: the family
must be confirmed free of look-ahead conditioning before being allowlisted.
It is — entry is regime-only, outcome is a forward first-touch.

## Data Flow

```
velocity parquet
  → run(): resolve_families includes "oco_asymmetric" when requested
  → _mine_frame_pair: for each (down_pips, rr, horizon) × regime
      entry_indices (regime bars) → measure_gross (asymmetric first-touch)
      → candidate row + random_entry_baseline
  → {symbol}_oco_asymmetric_candidates.csv
```

`resolve_families` gains an alias so `oco_asymmetric` can be mined — either a
new `library_type` value or an explicit `cfg["families"]` list (the plan
picks the least-invasive wiring).

## Error Handling

- `rr` or `down_pips` producing a non-positive barrier → `ValueError` at
  `param_grid` time.
- `_oco_asymmetric_precompute` on a frame too short for the horizon → empty
  `i0`, handled exactly as the symmetric engine handles it.
- Random-baseline degenerate cases inherit sub-project 0's `NaN` behaviour.

## Testing

- **Precompute parity:** with `up_pips == down_pips`,
  `_oco_asymmetric_precompute` must produce `gross` identical to
  `_oco_precompute_candidates` for the same barrier — pins the new engine to
  the trusted one.
- **No false edge:** on a driftless synthetic frame, asymmetric candidates'
  gross EV sits within the random-entry baseline noise band (small `|z|`) —
  confirms asymmetry alone is not a spurious edge.
- **Detects real structure:** on a synthetic frame with injected up-drift in
  one regime, that regime's wide-up-barrier candidates score `z > 0`.
- **Registry conformance:** `oco_asymmetric` satisfies the `MiningFamily`
  protocol; the family-allowlist contract test passes with the family added.

## Success Criterion

A candidate is real only if its gross EV beats the random-entry baseline
(roadmap shared criterion). The feature-importance / mining audit reports,
per regime, which `rr` (if any) clears the baseline — that is the output that
decides whether asymmetric barriers are worth carrying forward.

## File Map

- `scripts/mining_family.py` — add `OcoAsymmetricFamily`; register it.
- `scripts/run_tick_opportunity_mining.py` — add
  `_oco_asymmetric_precompute`; extend `resolve_families` wiring.
- `tests/test_oco_candidate_family_allowlist.py` — add `oco_asymmetric` to
  `ALLOWED_OCO_FAMILIES`.
- `tests/test_mining_family.py` — `oco_asymmetric` conformance + behaviour.
- `tests/test_tick_opportunity_mining.py` — precompute parity + edge-detection
  tests.

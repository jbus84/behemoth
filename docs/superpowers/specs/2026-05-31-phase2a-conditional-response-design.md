# Phase 2A — entry-conditioned conditional-response seeds + robustness-gated scoring — design

- Status: Proposed
- Date: 2026-05-31
- Relates to: the `vr_conditional_direction` NULL (`docs/analysis/era_fade_vr_conditional_2026-05-31.md`)
  and the Phase 2 sketch in `docs/superpowers/specs/2026-05-31-bayesian-edge-confidence-design.md`.
  `scripts/era_scalp/`.

## Goal

Fix the precise failure the null exposed — a global trailing variance-ratio threshold misclassifies the
mean-reverting majors at the tail-`|dev|` entry bars, because the *local* regime at a dislocation event
differs from the symbol's *average* regime. The fix has two parts:

1. **Entry-conditioned direction seeds:** a small seed family that picks the trade side per bar from a
   *causal, online* estimate of how the symbol's own past extreme dislocations resolved — not a trailing
   average. Direction is learned per symbol from completed history, with no peeking and no global
   threshold.
2. **Robustness-gated scorer:** the in-loop PUCT validation score currently takes `max` over the
   (q,h) grid — exactly the knife-edge selection that produced the `vr_conditional` q99/h100 mirage.
   Replace it with an aggregate that rewards consistency across the grid, so the search cannot win on a
   single lucky cell.

Validated with the EXISTING `bayes_edge` multi-(q,h) gate. The heavier Phase-2 pieces (fast in-loop
hierarchical posterior fit as the PUCT value; Thompson-sampling node selection) are **deferred** —
documented here, not built — because in every mode so far the literature seeds, not the LLM/PUCT search,
have produced the edge; the search engine is not the current bottleneck.

## Part 1 — conditional-response direction seeds

### Mechanism (causal, entry-conditioned)

The existing `_FAIR` block gives `dev = ew - p` (fair − mid, pips) and `p = cumsum(vel_pips_h1)` (the
causal mid path in pips). For a fade entered at past bar `j`, the realized outcome over horizon `h` is

```
fade_ret[j] = sign(dev[j]) * (p[j + h] - p[j])     # >0 => fading paid (price moved toward fair)
```

which is fully observable once bar `j+h` has passed. At bar `k`, every episode `j` with `j + h <= k`
is *completed* and usable. Restrict to *extreme* episodes (|dev[j]| in the trailing tail) since that is
where the fade enters. The running estimate

```
R[k] = mean( fade_ret[j]  over completed extreme episodes j, j + h <= k )
```

says whether fading extreme dislocations has been paying for THIS symbol up to bar `k`. The seed emits

```
out[k] = dev[k] * sign(R[k])      # R>0 => fade (+dev); R<0 => continue (-dev)
```

`|out| = |dev|`, so the harness top-q entry selection is unchanged; only the side is set, per-symbol,
from completed causal history. No global VR threshold; no look-ahead (R[k] uses only episodes resolved
strictly before k). It will fade EUR/AUD and continue GBP **iff** their own histories show that — the
entry-conditioned answer the null required.

Research grounding: empirical conditional-response / reversion function (Cont and co-authors on
price-impact response functions); online causal estimation of the event-conditioned outcome rather than
a trailing-average regime proxy.

### Seed variants (added to `FADE_SEED_PROGRAMS` in `scripts/era_scalp/fade_seeds.py`)

All reuse `_FAIR`, use an internal horizon `H=100` and an extreme gate, and MUST be O(n) — a naive
per-bar inner loop over past episodes is O(n^2) and will time out (a prior seed bug). Concretely:
- extreme gate: expanding mean + 2*std of `|dev|` via cumulative sums (the same O(n) construction as the
  existing `extreme_fade` seed), with a minimum-history guard (`m >= 60`);
- completed-episode outcome: `fade_ret[j] = sign(dev[j]) * (p[j+H] - p[j])` is a single shifted-array
  expression; mask it to extreme episodes; the running mean `R[k]` over episodes with `j+H <= k` is a
  cumulative sum of the masked `fade_ret` divided by a cumulative count, then shifted by `H` so bar `k`
  only sees episodes resolved by `k`. All O(n), no Python per-bar loop.
Each returns NaN until enough completed episodes exist (abstain).

- `conditional_response_fade` — `R[k]` = expanding causal mean of completed extreme-episode `fade_ret`.
- `conditional_response_decay` — `R[k]` = EWMA-weighted (recent completed episodes weigh more; adapts to
  regime drift).
- `conditional_response_signed` — maintain separate `R+[k]` / `R-[k]` for up- vs down-dislocations
  (`dev>0` vs `dev<0`); use the one matching `sign(dev[k])` (they can resolve asymmetrically).

Not added to `BASELINE_SEED_NAMES`. A `RESEARCH_IDEAS` line describes the conditional-response stream.

### Causality

Every term depends only on bars `<= k` (`p[<=k]`; episodes `j+h<=k`). The seeds pass the runtime
`causality_probe` (perturbing future rows leaves past output unchanged). This is the design's safety
gate against look-ahead; it does NOT test stationarity, but these seeds emit a signed multiple of `dev`
(a stationary mispricing), not a price level, so the fair-price spurious-regression failure mode does
not apply.

## Part 2 — robustness-gated scorer

`scripts/era_scalp/trade_score.py` `PooledTradeScorer.score` currently returns
`max` over `GRID_Q x GRID_H` of `pooled_task_score`. Add an `aggregate` parameter:

- `aggregate="max"` (DEFAULT) — unchanged, preserves all existing run reproducibility.
- `aggregate="robust"` — compute `pooled_task_score` for every (q,h) cell, then return
  `mean(cells) - std(cells)`. A program that is excellent in one cell and poor in the other eight scores
  *lower* than one that is consistently good, so the search is pushed toward grid-robust programs and
  away from knife-edge cells.

The change is confined to the cell-aggregation step (the per-cell `pooled_task_score` computation is
unchanged). Error/abort paths (`-1e6` on exec/static/causality failure) are unchanged. The full Bayesian
posterior remains the FINAL out-of-sample verdict via `bayes_edge` — it is not added to the in-loop
scorer (no per-program NUTS).

The `run_era_fade.py` driver passes `aggregate="robust"` and includes the new seeds among its roots, so
any actual search ranks on grid-robust validation score. (Validation of the seeds themselves does not
require a search — it uses `bayes_edge` directly, below.)

## Validation — the same multi-(q,h) gate the null introduced

For each new seed, run

```
uv run python -m scripts.era_scalp.bayes_edge --seed-name <seed> --q <q> --h <h>
```

at the grid points `(0.99,100)`, `(0.95,200)`, `(0.90,400)` across the 5 majors, and record the
per-symbol + pooled posterior. **Success criteria:**

- a seed is credibly positive (pooled `P(edge>0)` high, CI clear of 0) AND **robust** — it does not
  collapse to credibly-negative at a different (q,h), the failure that killed `vr_conditional_direction`;
- ideally it recovers EUR/AUD-fade and GBP-continue from the learned conditional response alone.

**Honest failure modes, reported plainly:** the learned `R` is too noisy at low completed-episode counts
(seed abstains too much / direction flips on noise); the conditional response is non-stationary so the
online estimate lags regime changes; or it works at one (q,h) only (same null as before). A null is a
result and is recorded.

## Files

- `scripts/era_scalp/fade_seeds.py` — MODIFY: add 3 conditional-response seeds + 1 `RESEARCH_IDEAS`
  line. Not added to `BASELINE_SEED_NAMES`.
- `scripts/era_scalp/trade_score.py` — MODIFY: add `aggregate` param (`"max"` default, `"robust"`).
- `scripts/era_scalp/run_era_fade.py` — MODIFY: pass `aggregate="robust"`; add the new seeds as roots.
- `tests/era_scalp/test_fade_seeds.py` — MODIFY: seed tests (below).
- `tests/era_scalp/test_trade_score.py` — MODIFY: scorer aggregate tests (below).
- `docs/analysis/era_regime_conditional_response_2026-05-31.md` — CREATE: the verdict evidence.

## Testing

Seed tests (synthetic, deterministic; reuse `_vel_ctx`/`_dev_ref` helpers already in the test file):
- **parse + causal**: covered automatically by the existing `test_all_seeds_run_causal` loop; each new
  seed also added to `test_expected_seeds_present` and `test_gated_seeds_abstain_sometimes`.
- **learns to FADE on a reverting history**: a synthetic series whose extreme dislocations historically
  revert => wherever finite (after warmup) `sign(out) == sign(dev)` for the base seed.
- **learns to CONTINUE on a trending history**: a synthetic series whose extreme dislocations
  historically continue => wherever finite (after warmup) `sign(out) == sign(-dev)` for the strict
  majority of bars.
- **magnitude invariant**: `|out| == |dev|` wherever finite.

Scorer tests:
- **robust penalises knife-edge**: a synthetic per-cell score vector that is high in one (q,h) cell and
  low in the rest yields a lower `"robust"` aggregate than `"max"`; a uniformly-good vector yields a
  `"robust"` aggregate close to its mean. (Test the aggregation directly with injected/seed signals so it
  is deterministic and fast.)
- **back-compat**: `aggregate="max"` reproduces the current score on a fixed seed signal.

## Consequences

- A principled, generalisable, entry-conditioned direction rule (learned per symbol from completed causal
  history) that is the correct successor to the failed global-VR rule, plus a scorer that no longer
  rewards grid knife-edges — both validated against the multi-(q,h) gate the null introduced.
- Standing caveat unchanged: all nets are mid-to-mid / flat-cost; the tick-exact realistic-round-trip
  cost gate remains the binding downstream check. A credible, robust Bayesian verdict here is necessary,
  not sufficient.
- Deferred (documented, not built): fast in-loop hierarchical posterior as the PUCT value, and
  Thompson-sampling node selection. Revisit only if the search becomes the bottleneck — so far it has not.

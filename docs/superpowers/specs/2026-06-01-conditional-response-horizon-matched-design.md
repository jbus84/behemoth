# Horizon-matched conditional-response family — design

- Status: Proposed
- Date: 2026-06-01
- Relates to: `docs/analysis/era_regime_conditional_response_2026-05-31.md` (Phase 2A, PR #284).
  `conditional_response_fade` was the best direction rule yet at the native horizon (q=0.99/h=100: pooled
  P=0.870, no symbol credibly negative) but collapsed at h=200/400. Diagnosis: it learns its conditional
  response `R` over a FIXED internal `H=100`, strongest exactly where internal-H == harness exit-h.
  `scripts/era_scalp/`.

## Goal

Test whether the parent seed's (q,h) fragility is a **horizon mismatch** (the learning horizon differs
from the holding horizon) rather than a genuinely horizon-specific edge. Do this by making the seed's
internal learning horizon match the harness exit horizon, then re-running the Bayesian gate with each
seed paired to its matched `--h`.

The dynamic per-symbol fade-vs-continue decision is UNCHANGED and already works: each seed learns `R[k]`
per symbol from that symbol's own completed extreme-dislocation episodes and fades when reversion has
paid, continues when it has not. This variant only changes the *horizon over which that outcome is
measured*, so the learned side is calibrated to the actual holding period.

## What changes (small)

The parent `conditional_response_fade` hardcodes `H = 100`. Refactor it through a generator so the only
thing that varies is the `H` literal:

```python
def _cond_response_src(H: int) -> str:
    return (
        "def signal(ctx):\n" + _FAIR +
        f"    H = {H}; W = 240; MINEP = 20\n"
        "    ad = np.abs(np.where(np.isfinite(dev), dev, 0.0))\n"
        ... (rest identical to the current conditional_response_fade body) ...
        "    return out\n"
    )
```

Register the family in `FADE_SEED_PROGRAMS`:
- `conditional_response_fade` = `_cond_response_src(100)` — behaviourally identical to the current seed
  (keeps existing tests and the PR #284 evidence valid).
- `conditional_response_fade_h200` = `_cond_response_src(200)`.
- `conditional_response_fade_h400` = `_cond_response_src(400)`.

`conditional_response_signed` is left exactly as-is (it was noise; not part of this experiment, not
extended). Nothing else changes — no scorer/engine change. The seeds remain causal, O(n), and
`|signal|=|dev|`; the generic test loops (`test_all_seeds_run_causal`, `test_gated_seeds_abstain_
sometimes`) cover the new family automatically once the two names are added to the literal lists.

## Validation — the matched-horizon gate

Pair each seed with its matched exit-h and sweep q ∈ {0.90, 0.95, 0.99}:

```bash
uv run python -m scripts.era_scalp.bayes_edge --seed-name conditional_response_fade       --h 100 --q <q>
uv run python -m scripts.era_scalp.bayes_edge --seed-name conditional_response_fade_h200  --h 200 --q <q>
uv run python -m scripts.era_scalp.bayes_edge --seed-name conditional_response_fade_h400  --h 400 --q <q>
```

across the 5 majors (9 runs total). **Success:** the matched-horizon strength (q99/h100's pooled ≈0.87,
no symbol credibly negative) holds across q AND across all three matched horizons — confirming the
parent's collapse was the internal-H≠exit-h mismatch. **Honest failure modes, reported plainly:** matched
runs still degrade at h200/h400 (the edge really was ~100-bar-specific), or the wider q at a matched h
turns a symbol credibly negative (knife-edge in q rather than h). A null is a result.

### Honesty note on the gate (state it in the verdict)
This is a MORE LENIENT criterion than the original Phase-2A gate: instead of requiring ONE signal to be
robust across all (q,h), it allows a DIFFERENT h-matched seed per holding horizon. That is a defensible
deployment model — you deploy the seed matched to the horizon you actually trade — but it must be stated
explicitly so the result is not over-read as the original "one robust signal" claim.

## Files

- `scripts/era_scalp/fade_seeds.py` — MODIFY: add `_cond_response_src(H)` generator; replace the
  `conditional_response_fade` entry with `_cond_response_src(100)`; add `_h200`, `_h400`; add a
  `RESEARCH_IDEAS` line on horizon-matching. Not added to `BASELINE_SEED_NAMES`.
- `tests/era_scalp/test_fade_seeds.py` — MODIFY: add the two new names to the presence + abstain literal
  lists; add one test that `_cond_response_src(H)` embeds the requested `H` (e.g. the h200 program text
  contains `H = 200`) and that the three family members all run causal with `|signal|=|dev|` and the
  expected reverting-history fade behaviour at their own H.
- `docs/analysis/era_conditional_response_horizon_matched_2026-05-31.md` — CREATE: the matched-horizon
  verdict evidence (filename keeps the 2026-05-31 analysis-series date for continuity with the parent).
- `scripts/era_scalp/bayes_edge.py` — reused unchanged.

## Testing

- **generator embeds H**: `"H = 200"` in `FADE_SEED_PROGRAMS["conditional_response_fade_h200"]`,
  `"H = 400"` in the h400 entry, `"H = 100"` in `conditional_response_fade`.
- **family runs causal + magnitude**: each of the three names passes `run_program` + `causality_probe`
  (covered by `test_all_seeds_run_causal`) and `|signal|=|dev|` wherever finite.
- **family learns fade on reverting history**: on `_ar_level_ctx()` each family member's fade-fraction >
  0.6 (reusing the existing helper), confirming the dynamic direction logic survives the H change.
- presence/abstain list tests extended with the two new names.

## Consequences

- A clean test of the horizon-mismatch hypothesis with no engine change and minimal new surface. If it
  holds, the h-matched family is the first entry-conditioned direction rule robust across horizons (under
  the matched-horizon deployment model) — the deployable successor to vr_gated_fade.
- Binding caveat unchanged: mid-to-mid / flat-cost; the tick-exact realistic-round-trip-cost gate remains
  the downstream check. A credible matched-horizon verdict is necessary, not sufficient.
- If it fails, we have a clean, honest answer (the edge is ~100-bar-specific) and stop chasing horizons.

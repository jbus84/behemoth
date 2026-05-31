# vr_conditional_direction seed — design

- Status: Proposed
- Date: 2026-05-31
- Relates to: the fade directional-regime finding (`docs/analysis/era_fade_bayes_verdict_2026-05-31.md`,
  PR #283). Flipping `vr_gated_fade` to continuation made GBP credibly positive (+1.96, P=1.000) while
  EUR/AUD stayed fade-positive — a real per-symbol directional regime split. This seed encodes that
  split as a single *causal* rule instead of a hand-assigned per-symbol direction. `scripts/era_scalp/`.

## Goal

One causal program whose trade *side* is chosen per-bar by the trailing variance ratio — **fade** when
the bar is clearly mean-reverting, **continue** when clearly trending — so the EUR/AUD-fade vs
GBP-continuation split we proved by hand emerges from a measurable regime variable **without the
program ever seeing the PnL sign**. Validate with the existing Bayesian edge layer across the 5 majors.

## Why this, not hand-assigned per-symbol direction

Picking EUR→fade, GBP→continue by looking at each symbol's realized sign is selection — it overfits and
does not generalise to a new symbol or period. Tying direction to a regime variable computed only from
past bars is a *single causal rule* with no per-symbol free parameters. The variance ratio is the
natural choice: it already gates `vr_gated_fade`, and the manual split lines up with it (EUR/AUD have
VR≈0.89 < 1 → reverting → fade; GBP has higher VR → trending → continue). The Bayesian layer then
reports whether the regime rule is credible — it is not told which direction to expect.

## The program (`signal(ctx)`)

Added to `FADE_SEED_PROGRAMS["vr_conditional_direction"]`. Reuses two existing, already-causal blocks:

- `_FAIR` → `dev = ew - p` (fair − mid, pips; >0 ⇒ mid below fair).
- the `vr_gated_fade` rolling variance-ratio machinery: `W=240`, `qv=20`, backward-window cumsum
  `rollvar`, giving per-bar `vr = vq / (qv*v1)` and window count `m`.

Then the direction rule (dead-band switch):

```python
out = np.full(n, np.nan)
ok = m >= 60
out = np.where(ok & (vr < 0.95), dev,  out)   # mean-reverting -> FADE (bet return to fair)
out = np.where(ok & (vr > 1.05), -dev, out)   # trending      -> CONTINUE (bet extension)
return out                                     # dead-band [0.95, 1.05] stays NaN = abstain
```

Properties:
- `|out| == |dev|` wherever finite, so the harness's top-q entry selection (`evaluate_trades`) is
  **regime-independent** — the same dislocation events fire; only the *side* (`sign(out)`) flips.
- Dead-band `[0.95, 1.05]` abstains (NaN), avoiding noise-driven side flip-flop where VR≈1.
- Fully causal: every term depends only on bars ≤ k (the `rollvar` windows look back only). Passes the
  runtime causality probe.

## Validation — the real test

Run the existing CLI, no plumbing change (it resolves `--seed-name` from `FADE_SEED_PROGRAMS`):

```bash
uv run python -m scripts.era_scalp.bayes_edge --seed-name vr_conditional_direction --q 0.99 --h 100
```

across the 5 majors (EURUSD, GBPUSD, AUDUSD, USDCHF, USDJPY). Headline at `q=0.99, h=100` to compare
like-for-like with the `vr_gated_fade` verdict. **Success criteria:**

- the regime rule recovers **credible positives** (P(edge>0) high, CI clear of 0) on the symbols where
  the manual direction won — EUR/AUD (fade) and GBP (continuation) — i.e. it picks the right side from
  VR alone, and
- pooled P(edge>0) **improves on the single-direction fade's 0.41**.

**Honest failure modes, reported plainly if they occur:** the dead-band abstains so much a symbol loses
its sample; VR mistimes a symbol's regime (e.g. picks fade for GBP) and kills its edge; or pooled stays
indistinguishable from zero because JPY/CHF remain noise. The seed is recorded either way — a null is a
result.

## Components / files

- `scripts/era_scalp/fade_seeds.py`: add `vr_conditional_direction` to `FADE_SEED_PROGRAMS`; add one
  line to `RESEARCH_IDEAS` describing regime-conditional direction. **Not** added to
  `BASELINE_SEED_NAMES` — this is not an ERA-search expansion.
- `tests/era_scalp/test_fade_seeds.py`: unit tests (see below).
- `docs/analysis/era_fade_vr_conditional_2026-05-31.md`: the Bayesian verdict evidence + comparison to
  the fade and continuation verdicts.
- `scripts/era_scalp/bayes_edge.py`: reused unchanged.

## Testing

Unit (pytest, synthetic + deterministic):
- **parses + causal**: `run_program(src, ctx, required_fn="signal")` returns no error and the seed
  passes `causality_probe` (perturbing future rows leaves past output unchanged).
- **fade in reverting regime**: on a synthetic strongly mean-reverting price series (so trailing
  `vr < 0.95`), wherever `out` is finite `sign(out) == sign(dev)`.
- **continue in trending regime**: on a synthetic strongly trending series (`vr > 1.05`), wherever
  `out` is finite `sign(out) == sign(-dev)`.
- **dead-band abstains**: construct/window a region with `0.95 <= vr <= 1.05` → `out` is NaN there.
- **magnitude preserved**: `np.abs(out) == np.abs(dev)` wherever `out` is finite.

Integration: the `bayes_edge` run above is an evidence run (not a pytest) — it needs the real velocity
parquets and writes the markdown verdict.

## Consequences

- A principled, generalisable encoding of the directional-regime finding: direction is earned from a
  causal regime variable, not fitted per symbol. If credible, it is the deployable form of the EUR/AUD +
  GBP edge and a natural future ERA-search root / Phase-2 PUCT seed (regime-conditional direction).
- The standing caveat is unchanged: all nets are mid-to-mid / flat-cost. Continuation bars pay the
  spread *against* entry (already in `evaluate_trades`'s `-cost`), but the tick-exact realistic-cost
  gate remains the binding downstream check. A credible Bayesian verdict here is necessary, not
  sufficient.

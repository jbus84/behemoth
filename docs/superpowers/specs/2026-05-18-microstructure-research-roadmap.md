# Microstructure Research Roadmap

**Date:** 2026-05-18
**Status:** Approved (roadmap)
**Type:** Umbrella index — each sub-project below gets its own spec + plan.

## Problem Context

The OCO `first_touch` library produces no tradeable edge:

- PR #173 removed the look-ahead-biased `first_touch_clean` family. The
  apparent OCO signal (AUC ~0.57 in older reports) was an artifact of that
  bias — its candidate universe was conditioned on a forward-looking
  `~both` filter.
- The surviving honest family, `oco_first_touch`, was scanned across all
  4,080 mined candidates (6 symbols × barriers × horizons × regimes):
  **0 candidates are positive on both train and test splits.**
- `p_up_first` (probability the up-barrier is touched first) has median
  0.499 and a p5–p95 range of 0.46–0.52 — first-touch direction is a coin
  flip in every regime, at every barrier width, at every horizon.

First-touch carries no information. Any edge must come from a *conditional
sequence* of events or an *asymmetric payoff*, not from predicting which
barrier is hit first. This roadmap pursues five such research directions
behind one shared evaluation bar.

## Success / Kill Criterion (shared)

A research family is a **success** if its mined candidates show gross EV
*statistically above a random-entry baseline* on the same bars: entry timing
is shuffled/randomised on the identical bar set and the control gross-EV
distribution is computed, so each family's candidates can be scored as N
standard deviations above random.

A family that cannot beat random entry is **abandoned** — it carries no
signal, regardless of split-luck appearances.

This is pre-cost (gross). Proving raw signal exists comes before worrying
about execution cost; net-of-cost evaluation is deferred to whichever
families clear this bar.

## Sub-Projects

### 0. Mining family framework + random-entry baseline

`scripts/run_tick_opportunity_mining.py` currently hardcodes the
`oco_first_touch` and `directional` families. This sub-project adds:

- A registration seam so a new candidate family supplies its own entry
  trigger, target definition, and outcome measurement without editing the
  core mining loop.
- A random-entry baseline harness: for any family, shuffle/randomise entry
  timing on the same bar set, compute the control gross-EV distribution, and
  score each candidate's gross EV against it.

Infrastructure, not research. Prerequisite for all sub-projects below.

### 1. Asymmetric barriers

Extends the existing OCO grid with a `tp_pips ≠ sl_pips` axis. Even with a
50/50 first-touch, payoff asymmetry changes EV — a momentum regime with wide
TP / tight SL, or a mean-revert regime with the opposite. Cheapest family;
reuses most of the existing OCO mining path.

### 2. Consecutive-move persistence

Continuation after N consecutive same-sign tick-bars. Features
(`directional_persistence_8`, `signed_flow_24`) already exist. A fast
falsification check — directional single-bar AUC is already 0.50, so this
must show that conditioning on a run of N changes continuation probability.

### 3. Double-touch / liquidity sweep

New family. Entry conditional on barrier A being touched then barrier B being
touched (a stop-hunt / false-breakout sweep); target is continuation past B.
Motivated by `both_window_rate` reaching 0.80 in some regimes — those regimes
are where A→B sequences live. Edge is conditional on a completed sweep, not a
coin-flip prediction.

### 4. Pullback continuation

New family. After an impulse of size M, a retracement of fraction R, then
resumption past the impulse extreme. Target is `P(resume original direction |
pullback depth, pullback duration, regime)`. Edge is conditional on a
completed impulse + pullback.

### 5. No-touch / sell-the-range

New family. The honest inverse of OCO first-touch: profit when *neither*
barrier is touched within the horizon (range-bound regime). `both_window_rate`
and the no-touch rate vary across regimes, unlike first-touch direction.

## Dependency Graph & Sequence

```
        0  (framework + random-entry baseline)
       /|\
      / | \___________
     /  |             \
    1   2              3 ──► 4 ──► 5
 (asym) (persist)   (double)(pullbk)(no-touch)
```

- **0** is a hard prerequisite for **1–5**.
- **1** and **2** are cheap and independent — run them in parallel right
  after 0. They either surface quick signal or rule themselves out.
- **3 → 4 → 5** are the three substantive new families, sequenced after the
  cheap checks so that lessons from the framework and the cheap families
  inform the heavier work.

## Status

| # | Sub-project | Spec | Plan | Status |
|---|---|---|---|---|
| 0 | Mining family framework + random-entry baseline | [design](2026-05-18-mining-family-framework-design.md) | [plan](../plans/2026-05-18-mining-family-framework.md) | Planned |
| 1 | Asymmetric barriers | — | — | Blocked on 0 |
| 2 | Consecutive-move persistence | — | — | Blocked on 0 |
| 3 | Double-touch / liquidity sweep | [design](2026-05-18-double-touch-sweep-design.md) | — | Specced |
| 4 | Pullback continuation | [design](2026-05-18-pullback-continuation-design.md) | — | Specced |
| 5 | No-touch / sell-the-range | — | — | Blocked on 0 |

Each sub-project gets its own `docs/superpowers/specs/` design and
`docs/superpowers/plans/` implementation plan. This table is updated as each
is specced, planned, and completed.

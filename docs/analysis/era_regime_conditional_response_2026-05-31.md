# ERA fade — conditional-response (entry-conditioned) Bayesian verdict (2026-05-31)

Side learned per-bar from a causal online mean `R[k]` of how the symbol's own past EXTREME dislocations
resolved over an internal horizon `H=100` bars (completed episodes only, written at resolution index
`j+H`; O(n)). Fade when reversion has paid, continue when it has not. The regime is measured at the
event and learned per symbol with no peeking — the fix the `vr_conditional_direction` null demanded.
Validated against the same multi-(q,h) robustness gate.

## conditional_response_fade — multi-(q,h)

| grid | pooled P(edge>0) | EUR | AUD | GBP | CHF | JPY |
|---|---|---|---|---|---|---|
| q=0.99, h=100 | **0.870** (+0.39) | 0.947 (+0.60) | 0.630 (-0.19) | 0.830 (+1.41) | 0.863 (+1.13) | 0.757 (+0.12) |
| q=0.95, h=200 | 0.203 (-0.32) | 0.266 | 0.382 | 0.032 (neg) | 0.554 | 0.748 |
| q=0.90, h=400 | 0.019 (-0.71) | 0.001 (neg) | 0.048 (neg) | 0.049 (neg) | 0.847 | 0.000 (neg) |

## conditional_response_signed — multi-(q,h)

| grid | pooled P(edge>0) | EUR | AUD | GBP | CHF | JPY |
|---|---|---|---|---|---|---|
| q=0.99, h=100 | 0.003 (-1.06) | 0.021 (neg) | 0.009 (neg) | 0.001 (neg) | 0.210 | 0.001 (neg) |
| q=0.95, h=200 | 0.343 (-0.15) | 0.981 (+1.53) | 0.000 (neg) | 0.097 | 0.949 | 0.787 |
| q=0.90, h=400 | 0.777 (+0.35) | 1.000 (+1.42) | 0.332 | 0.896 | 0.669 | 0.600 |

## Comparison vs prior verdicts (q=0.99, h=100)

| | pooled P(edge>0) | EUR | AUD | GBP | any credibly NEGATIVE? |
|---|---|---|---|---|---|
| vr_gated_fade            | 0.410 | 0.994 | 0.983 | 0.072 (neg) | yes (GBP) |
| vr_conditional_direction | 0.511 | 0.508 | 0.050 (neg) | 0.985 | yes (AUD) |
| **conditional_response_fade** | **0.870** | 0.947 | 0.630 | 0.830 | **NO — all 5 lean positive** |
| conditional_response_signed   | 0.003 | 0.021 (neg) | 0.009 (neg) | 0.001 (neg) | yes (all) |

## Verdict — best result yet at the native horizon; NOT robust across (q,h); fragility is a fixable horizon mismatch

**`conditional_response_fade` is the strongest direction rule found so far** — but only at the matched
horizon, and it still fails the strict multi-(q,h) robustness gate.

- At **q=0.99, h=100** it gives pooled P(edge>0)=0.870 (+0.39 pips) and, uniquely, **no symbol is
  credibly negative** — every major leans positive. Neither `vr_gated_fade` (GBP credibly negative) nor
  `vr_conditional_direction` (AUD credibly negative) achieved that. The entry-conditioned learning did
  what it was meant to: it set each symbol's direction from its own completed history without breaking
  any symbol. Pooled CI still straddles 0, so this is "broadly positive, not yet credibly positive
  pooled" — an honest improvement, not a win.
- But it **collapses to credibly-negative pooled at q=0.90, h=400** (P=0.019; EUR/AUD/JPY credibly
  negative), the same knife-edge failure that killed `vr_conditional_direction`. `conditional_response_
  signed` is worse still — it flips the sign of the pooled edge across the grid (credibly negative at
  q99/h100, positive-leaning at q90/h400), so the up/down split adds noise, not signal, here.

**The likely cause is concrete and fixable.** The seed learns its conditional response at a FIXED
internal `H=100`, but the harness exits at `h ∈ {100, 200, 400}`. The result is strong exactly where
internal-H equals the exit-h (q99/h100) and decays as the two diverge (h=200, h=400). So a large part of
the (q,h) fragility is a **horizon mismatch between the learning horizon and the exit horizon**, not
necessarily an absence of edge at longer horizons.

**Status: NULL on the strict robustness gate, but the most promising direction rule to date.** Recorded
as such — a null is a result, and this one carries a clear next experiment.

### Next step (not built here)
Tie the seed's internal learning horizon to the harness exit horizon (learn `R` over the same `h` the
trade is held), e.g. a horizon-matched variant or a per-h family, then re-run this exact multi-(q,h)
gate. If the matched-horizon result holds across the grid, this becomes the first robust entry-
conditioned edge. The binding caveat is unchanged: all nets are mid-to-mid / flat-cost; the tick-exact
realistic-round-trip-cost gate remains the downstream check before any of this is real.

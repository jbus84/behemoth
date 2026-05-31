# ERA fade — vr_conditional_direction Bayesian verdict (2026-05-31)

Single causal seed: side chosen per-bar by trailing variance ratio — fade (`dev`) when VR<0.95,
continue (`-dev`) when VR>1.05, abstain in the [0.95,1.05] dead-band. `|signal|=|dev|` so entry
selection is regime-independent; only the side flips. **No per-symbol direction fitting** — direction
is a deterministic function of a regime variable computed without seeing PnL. This is the principled
test of whether the hand-found EUR/AUD-fade + GBP-continuation split is capturable by one causal rule.

## Headline (q=0.99, h=100), 5 majors

| symbol | P(edge>0) | mean (pips) | 94% CI |
|---|---|---|---|
| EURUSD | 0.508 | +0.281 | [-0.457, +2.716] |
| GBPUSD | 0.985 | +1.643 | [+0.916, +2.106] |
| AUDUSD | 0.050 | -1.310 | [-2.500, +0.105] |
| USDCHF | 0.037 | -0.618 | [-1.143, +0.055] |
| USDJPY | 0.436 | +0.039 | [-1.385, +1.503] |
| **Pooled** | **0.511** | **+0.003** | **[-0.713, +0.740]** |

## Comparison vs prior verdicts (q=0.99, h=100)

| | pooled P(edge>0) | EUR | AUD | GBP |
|---|---|---|---|---|
| fade (vr_gated_fade)         | 0.410 | 0.994 (+1.16) | 0.983 (+1.02) | 0.072 (neg) |
| continuation (flipped)       | 0.086 | 0.000         | 0.000         | 1.000 (+1.96) |
| **vr_conditional_direction** | 0.511 | 0.508 (+0.28) | 0.050 (NEG)   | 0.985 (+1.64) |

## Robustness across (q, h) — the decisive check

| grid | pooled P(edge>0) | EUR | AUD | GBP |
|---|---|---|---|---|
| q=0.99, h=100 | 0.511 | 0.508 | 0.050 | 0.985 |
| q=0.95, h=200 | **0.000** | 0.001 | 0.000 | **0.000** |
| q=0.90, h=400 | 0.228 | 0.434 | 0.413 | 0.158 |

At q=0.95/h=200 **every symbol is credibly negative** (pooled P=0.000); at q=0.90/h=400 all symbols are
negative-or-noise and GBP is no longer positive. The only credible positive anywhere — GBP at
q=0.99/h=100 — does **not** survive a change of entry quantile or horizon.

## Verdict — NULL (the regime rule does not generalise the hand-found split)

The single causal VR-conditional direction rule **fails the robustness gate**. It recovered GBP's
continuation edge at one knife-edge grid point (q=0.99/h=100, P=0.985) but:

1. **broke AUDUSD** — its credible fade edge (+1.02, P=0.983) flipped to a credibly *negative* −1.31,
   because at the q=0.99 |dev| extremes AUD's trailing VR is often >1.05, so the rule switches it to
   continuation on exactly its best fade bars;
2. **weakened EURUSD** to a coin-flip (P=0.508); and
3. **did not survive** at q=0.95/h=200 (all credibly negative) or q=0.90/h=400 (GBP negative).

The lesson is precise and useful: **trailing variance ratio and dislocation extremity are not
independent.** At the tail-`|dev|` bars where the fade actually enters, the local VR regime is not the
symbol's average regime, so a global VR threshold misclassifies the mean-reverting majors. The
hand-assigned per-symbol direction (EUR/AUD fade, GBP continue) worked precisely *because* it was
fitted per symbol — it does not reduce to one causal regime variable. Replacing the hand-assignment
with an honest, peek-free rule makes most of the apparent edge evaporate.

This is the Bayesian + robustness discipline doing its job: it prevented deploying a knife-edge mirage.
The most robust credibly-positive result on this data remains the **EUR/AUD fade** from `vr_gated_fade`
at q=0.99/h=100 — and **even that** is mid-to-mid / flat-cost and still owes the tick-exact
realistic-round-trip-cost gate, which is the binding downstream check before any of this is real.

### What a future attempt would need (not built here)
A regime variable that is *conditioned on the entry event* rather than a trailing average — e.g. the
sign of post-dislocation drift estimated causally, a per-symbol VR threshold learned out-of-sample, or
the Phase-2 Bayesian-PUCT search over regime features — and it must clear this same multi-(q,h)
robustness gate, not a single point.

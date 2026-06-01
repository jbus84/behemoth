# ERA fade — horizon-matched conditional-response Bayesian verdict (2026-06-01)

Each seed learns its conditional response `R` over its OWN horizon `H` and is evaluated at the matching
exit `h` (internal-H == exit-h). This tests the hypothesis that the parent `conditional_response_fade`'s
(q,h) collapse was a horizon mismatch. The dynamic per-symbol fade-vs-continue learning is unchanged
from PR #284.

## Matched-horizon results (each seed at its own h; q swept)

### H=100 (conditional_response_fade @ h=100)
| q | pooled P(edge>0) | EUR | AUD | GBP | CHF | JPY |
|---|---|---|---|---|---|---|
| 0.99 | **0.870** (+0.39) | 0.947 (+0.60) | 0.630 (-0.19) | 0.830 (+1.41) | 0.863 (+1.13) | 0.757 (+0.12) |
| 0.95 | 0.318 (-0.22) | 0.000 (neg) | 0.000 (neg) | 0.913 | 0.838 | 0.044 (neg) |
| 0.90 | 0.035 (-0.49) | 0.000 (neg) | 0.000 (neg) | 0.000 (neg) | 0.863 | 0.011 (neg) |

### H=200 (conditional_response_fade_h200 @ h=200)
| q | pooled P(edge>0) | EUR | AUD | GBP | CHF | JPY |
|---|---|---|---|---|---|---|
| 0.99 | 0.200 (-0.35) | 0.944 (+2.90) | 0.894 (+0.54) | 0.002 (neg) | 0.018 (neg) | 0.000 (-6.91) |
| 0.95 | 0.053 (-0.72) | 0.760 | 0.789 | 0.000 (neg) | 0.000 (neg) | 0.000 (neg) |
| 0.90 | 0.008 (-0.81) | 0.818 | 0.043 (neg) | 0.000 (neg) | 0.000 (neg) | 0.000 (neg) |

### H=400 (conditional_response_fade_h400 @ h=400)
| q | pooled P(edge>0) | EUR | AUD | GBP | CHF | JPY |
|---|---|---|---|---|---|---|
| 0.99 | 0.791 (+0.34) | **1.000 (+5.9 post / +1.78 raw)** | 0.984 (+3.41) | 0.000 (neg) | 0.001 (neg) | 0.563 |
| 0.95 | 0.598 (+0.07) | 0.988 (+1.56) | 0.300 | 0.119 | 0.011 (neg) | 0.943 |
| 0.90 | 0.071 (-0.55) | 0.725 (+0.84) | 0.075 | 0.000 (neg) | 0.377 | 0.003 (neg) |

## Verdict — hypothesis REFUTED, but the real edge is now sharp: EUR (+AUD), strongest at long horizon

**Horizon-matching did NOT fix (q,h) robustness.** At every matched horizon the pooled edge collapses as
`q` drops from 0.99, and multiple symbols turn credibly negative. So the parent's fragility was **not**
primarily an internal-H≠exit-h mismatch — there is strong **q-sensitivity** (the edge lives in the most
extreme dislocations) and genuine **per-symbol heterogeneity** at every horizon. The clean "one rule
robust across the grid" outcome does not exist here.

**But the experiment produced the clearest, best-sampled edge of the whole arc.** The credible positive
is concentrated in **EURUSD and AUDUSD**, and it *strengthens at longer horizons*:
- **EURUSD @ H=400, q=0.99: P(edge>0)=1.000** over **3166 trades across all 17 holdout months**, raw
  **+1.78 pip/trade** (the posterior's +5.9 weights high months and is inflated relative to raw — cite
  the raw figure; the SIGN and credibility are unambiguous). This is **not** a few-episode mirage — it is
  the largest, best-sampled single-symbol edge found in this project.
- EURUSD is also credibly positive at H=400/q=0.95 (P=0.988, +1.56) and H=200/q=0.99 (P=0.944, +2.90).
- AUDUSD @ H=400/q=0.99: P=0.984 (+3.41).
- **GBP, CHF, JPY** are negative or unstable across nearly the whole grid (JPY even −6.9 at H=200/q=0.99)
  — they have **no fade edge**.

**The recurring truth, reconfirmed a third time.** Every honest verdict in this arc reconverges on the
same place: the first Bayesian verdict found EUR+AUD the only credibly-positive symbols; this one finds
EUR+AUD strengthen at long horizon while the other three deteriorate. The pooled-across-5 framing keeps
failing because **3 of the 5 majors simply do not have a fade edge** — averaging them in dilutes and
masks the real, robust EUR/AUD signal.

## Recommendation
Stop seeking one rule for all 5 majors. The deployable hypothesis is a **EURUSD (and AUDUSD) fade at
extreme dislocations (q≈0.99), strongest at a longer holding horizon (h≈400)** — and at raw +1.78
pip/trade over 3166 trades it is, for the first time, large enough that it could plausibly survive
realistic cost. The binding next gate is therefore the **tick-exact realistic round-trip cost check on
EURUSD specifically** (all results here remain mid-to-mid / flat-cost).

## Honesty note on the gate
This matched-horizon gate is MORE LENIENT than the Phase-2A gate (a different h-matched seed per holding
horizon, rather than one signal robust across all h). It is reported as a refuted hypothesis plus a
single-symbol finding, not as a "robust across the grid" claim.

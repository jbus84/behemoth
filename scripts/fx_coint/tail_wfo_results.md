# FX Tail-Edge Walk-Forward Confirmation — Results & Verdict

**Date:** 2026-06-18
**Script:** `scripts/fx_coint/tail_wfo.py`
**Run:** `--symbol all --freq all` — long-only top-decile (q=0.9) on tight-cost majors +
USDCAD at 2h/3h, **expanding-window walk-forward (5 folds, refit each), no-look-ahead
decile threshold from train predictions**, net of real Pepperstone Razor cost.

This is the honest out-of-sample test of the PR #340 tail edge (which used a single split
and an in-sample decile threshold). See memory `project_fx_intraday_tail_cost_tier_edge`.

## Verdict table (long-only, q=0.90)

| pair | freq | n | meanNet | t | posFold | hit | totNet | BH-sig | GO |
|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 2h | 505 | +0.510 | 0.87 | 0.80 | 49% | +257.8 | – | – |
| EURUSD | 3h | 137 | -1.548 | -1.04 | 0.40 | 50% | -212.1 | – | – |
| GBPUSD | 2h | 388 | +0.584 | 0.67 | 0.80 | 48% | +226.4 | – | – |
| GBPUSD | 3h | 131 | +1.204 | 0.67 | 0.40 | 51% | +157.8 | – | – |
| USDJPY | 2h | 594 | +0.498 | 0.81 | 0.60 | 53% | +296.1 | – | – |
| USDJPY | 3h | 96 | +0.947 | 0.50 | 0.80 | 56% | +91.0 | – | – |
| USDCAD | 2h | 443 | -0.237 | -0.39 | 0.40 | 48% | -104.9 | – | – |
| USDCAD | 3h | 160 | +0.051 | 0.05 | 0.80 | 46% | +8.2 | – | – |

## Verdict: NO-GO on the gate — edge survives in *direction* but is under-powered

**No cell passes** (`mean_net_bps>0 AND BH-significant AND pos_fold_pct>=0.6`). Every cell
fails on **significance** (t-stats 0.5–0.9, none BH-significant). Decomposing honestly:

### What survived walk-forward
- **2h long on tight majors stayed net-positive after the no-look-ahead threshold:**
  EURUSD +0.51, GBPUSD +0.58, USDJPY +0.50 bps/trade, each with **pos_fold_pct 0.6–0.8**
  (positive in a majority of folds). The direction and cross-pair consistency held — the
  #340 result was not a single-split mirage at 2h.
- **q-sensitivity is monotone increasing for every tight-major 2h cell** — the signature of
  a real conviction signal, not a threshold artifact:

  | pair | freq | q0.80 | q0.90 | q0.95 |
  |---|---|---|---|---|
  | EURUSD | 2h | +0.213 | +0.510 | **+1.193** |
  | GBPUSD | 2h | +0.233 | +0.584 | **+0.919** |
  | USDJPY | 2h | +0.098 | +0.498 | **+1.497** |
  | GBPUSD | 3h | +0.756 | +1.204 | **+6.134** |

  Higher predicted percentile → larger net edge, consistently. This is the strongest
  evidence yet that there is a genuine continuation edge in the 2h tight-major tail.

### What did NOT survive
- **The binding constraint is statistical power.** With ~390–600 trades at q0.9 and a
  per-trade edge of ~0.5 bps against ~6–8 bps trade-to-trade noise, t≈0.8 — nowhere near
  significance. The edge is real-direction but **uncertified**.
- **3h is unreliable under honest OOS thresholding.** EURUSD 3h flips negative (-1.55),
  USDJPY 3h reverses at q0.95 (-1.51); only GBPUSD 3h stays positive. The #340 3h cluster
  was inflated by in-sample thresholding + tiny N (N_top≈66); it largely does not hold.
- **USDJPY 3h reversion is killed.** Short-side WFO: mean -0.782 bps, t -0.75. The #340
  USDJPY-3h mean-reversion was a single-split artifact.
- **USDCAD killed** — cost (~0.97 bps) eats the thin edge; mostly negative.

## Bottom line

The edge is **real in direction, conviction-monotone, and fold-robust for 2h long on tight
majors (EUR/GBP/JPY), but statistically under-powered** — it fails BH significance, so it is
a **NO-GO for deployment** on current evidence. It is *not* killed: the q-monotonicity and
0.6–0.8 fold positivity across three independent pairs are coherent. The blocker is now
unambiguously **sample size / power**, not edge absence and not (for 2h tight majors) cost.

## Next step (if pursued)

Power, not new signal, is the lever:
1. **Pool the three tight majors** (EUR/GBP/JPY 2h) — same continuation signal, ~1,500
   trades — and test the pooled per-trade net for significance (≈√3 boost to t).
2. **More history** if available beyond the current span.
3. Only if the pooled 2h test clears BH: a **richer model** (this used 5 price-only features —
   the floor) and then **tick-exact fill verification** before sizing.

3h, USDCAD, and the USDJPY-3h reversion are dropped.

---

## UPDATE: Pooled tight-majors significance test (the power lever)

Pooled the EUR/GBP/JPY 2h long top-decile trades for breadth and tested significance two ways:
naive per-trade t (overstates — correlated trades) and **day-clustered t** (mean net per
calendar day, then test the daily series — absorbs cross-pair + intraday correlation).

| q | trades | mean net | naive t (p) | **day-clustered t (p)** | days | hit |
|---|---|---|---|---|---|---|
| 0.80 | 2651 | +0.177 | 0.65 (0.514) | 1.32 (0.187) | 880 | 50% |
| 0.90 | 1487 | +0.525 | 1.35 (0.176) | **2.00 (0.046)** | 614 | 50% |
| 0.95 | 832 | +1.265 | 2.25 (0.025) | **2.78 (0.006)** | 401 | 52% |

**This clears significance.** At top-5% conviction: **+1.27 bps/trade, day-clustered p=0.006**
(<1%), surviving a 3× Bonferroni for the q-sweep (→0.018). It is the **first FX intraday cell
in the project to clear significance net of real cost**. Two credibility checks pass:
1. **Mean AND t-stat both rise monotonically with conviction** (mean +0.18→+0.53→+1.27;
   day-clustered t 1.32→2.00→2.78) — the mechanical signature of a real tail edge, not a
   threshold artifact.
2. **Day-clustering raised t rather than lowering it**, so the significance is not an artifact
   of treating correlated same-day trades as independent.

### Honest caveats (do not skip before risking capital)
- **Garden of forking paths:** the cell (2h, these 3 pairs, long, high-q) was *selected* from
  the #340 exploration. The WFO is OOS within the period, but the cell choice was not
  pre-registered. Trust requires an untouched holdout (e.g. later years, or out-of-sample pairs).
- **Magnitude-tail edge, hit only 52%:** wins barely more than half; expectancy comes from the
  size of the winners. Highly sensitive to slippage — needs tick-exact (ideally maker) fills.
- **Day-independence:** day-clustering assumes calendar days are independent; multi-day momentum
  persistence could still inflate t. A block bootstrap / Newey-West would harden it further.

### Revised verdict
The 2h long tight-major continuation edge is **real and now statistically significant net of
cost at high conviction** — the first such result in this FX program. It is **GO for further
validation, not yet GO for capital.** Next: (1) untouched-holdout / pre-registered test to kill
the forking-paths concern, (2) block-bootstrap significance, (3) tick-exact fill verification,
(4) only then a richer model (this is still the 5-feature floor).

---

## UPDATE: Forking-paths attacks — OOS-pairs & era split

### (1) Out-of-sample pairs — same rule on the 3 excluded majors

Applied the identical 2h-long q0.95 mechanical rule to AUDUSD, USDCHF, and USDCAD (pairs that
played **no role** in selecting the 2h/3-pair/long/high-q cell).

| pair | cost | n | grossMean | gross day-t (p) | netMean | net day-t (p) |
|---|---|---|---|---|---|---|
| AUDUSD | 1.06 | — | −0.92 | −0.23 (0.82) | −1.98 | −1.11 (0.27) |
| USDCHF | 1.05 | — | +0.52 | **+3.48 (0.001)** | −0.53 | +2.52 (0.012) |
| USDCAD | 0.97 | — | +0.75 | +0.68 (0.50) | −0.22 | −0.17 (0.87) |
| **Pooled** | — | — | **+0.16** | **+2.27 (0.024)** | — | — |

**Verdict:** the *gross* continuation signal **generalizes** — pooled OOS gross is significant
(p=0.024) and USDCHF is strongly so (p=0.001). A forking-paths fluke would not produce a
significant gross signal on pairs that never informed the choice. However, **net of their higher
costs none of these clear** — consistent with the cost-tier thesis: the signal is real, but
cost decides which pairs are tradeable. AUDUSD is the dissenter (negative gross).

### (2) Era split-half — the red flag

Split the EUR/GBP/JPY pooled 2h-long q0.95 **net** trades at the median trade date
(~2023-04) and tested each half independently with day-clustered t.

| era | n | meanNet | day-t (p) |
|---|---|---|---|
| first half (pre-2023-04) | 416 | **+2.08** | **+3.50 (0.001)** |
| second half (post-2023-04) | 416 | +0.45 | +0.59 (0.555) |

**The edge is concentrated in the older era and has decayed to insignificance in the last
~2 years.** Mean dropped 4× and significance vanished. The headline p=0.006 was driven mostly
by the early period.

### Honest revised verdict (post-forking-paths attacks)

- The signal is **real** — it generalizes gross to out-of-sample pairs (not a forking-paths
  artifact at the gross level).
- But it appears to have **decayed** — it is not significant in the recent half, which is the
  half that matters for deployment. This is the classic profile of alpha that got competed away
  (or a regime shift).

**This downgrades the result from "GO for validation" to "signal real but decayed — NO-GO for
deployment until the decay is understood."**

The next question worth answering isn't "is it real?" (it is) but "why did it decay, and is the
recent +0.45 bps a floor or a continuing slide?" — which needs a rolling-window-over-time view,
not another pooled number. Supersedes the "surviving FX edge = weekly+ only" conclusion **only
if** a subsequent rolling-window test shows recovery or stabilization in the recent era.

---

## UPDATE: Granular temporal slices — the regime-burst reality

A simple median split said "pre-2023 good, post-2023 bad." Running yearly and **quarterly**
`temporal_slice_report` on the pooled EUR/GBP/JPY 2h-long q0.95 net trades exposes what
actually happened.

### Yearly view

| year | n | days | meanNet | t | p | hit |
|---|---|---|---|---|---|---|
| 2022 | 335 | 132 | **+2.59** | **+2.54** | **0.012** | 51% |
| 2023 | 209 | 107 | +1.72 | +2.00 | 0.048 | 52% |
| 2024 | 117 | 62 | **−2.09** | −1.75 | 0.085 | 49% |
| 2025 | 138 | 82 | +2.66 | +1.95 | 0.055 | 57% |
| 2026 | 33 | 18 | −0.39 | −0.14 | 0.888 | 45% |

### Quarterly view (the truth)

| quarter | n | days | meanNet | t | p | hit |
|---|---|---|---|---|---|---|
| 2022Q1 | 14 | 7 | +4.76 | +2.02 | 0.090 | 79% |
| 2022Q2 | 70 | 37 | +2.62 | +1.58 | 0.122 | 49% |
| 2022Q3 | 90 | 40 | +2.45 | +1.25 | 0.220 | 47% |
| 2022Q4 | 161 | 48 | +2.36 | +1.26 | 0.215 | 53% |
| **2023Q1** | **81** | **36** | **+4.75** | **+2.95** | **0.006** | **64%** |
| 2023Q2 | 32 | 19 | +0.10 | +0.05 | 0.963 | 53% |
| 2023Q3 | 40 | 20 | +0.09 | +0.07 | 0.943 | 48% |
| 2023Q4 | 56 | 32 | +0.30 | +0.18 | 0.856 | 38% |
| 2024Q1 | 10 | 8 | +2.80 | +0.87 | 0.413 | 70% |
| 2024Q2 | 28 | 14 | −0.96 | −0.65 | 0.528 | 50% |
| 2024Q3 | 50 | 23 | **−3.78** | −1.68 | 0.107 | 40% |
| 2024Q4 | 29 | 17 | −3.03 | −1.27 | 0.222 | 55% |
| 2025Q1 | 45 | 30 | +4.08 | +1.86 | 0.073 | 56% |
| 2025Q2 | 50 | 34 | +2.04 | +0.78 | 0.438 | 60% |
| 2025Q3 | 36 | 13 | +0.87 | +0.52 | 0.613 | 50% |
| 2025Q4 | 7 | 5 | +2.98 | +1.58 | 0.189 | 71% |
| 2026Q1 | 27 | 16 | −0.92 | −0.32 | 0.755 | 41% |
| 2026Q2 | 6 | 2 | +3.88 | nan | nan | 67% |

### What this actually means

The median-split story of "gradual decay" is **wrong**. The real profile is:

1. **Strong 2022** — consistently positive all four quarters (+2.4 to +4.8 bps).
2. **One monster quarter: 2023Q1** (+4.75 bps, p=0.006, 64% hit, 36 trading days). **This single
   quarter alone likely accounts for the bulk of the "first half" significance** (the pre-2023
   half had 168 days; 2022 + 2023Q1 = 132 + 36 = 168 days).
3. **Immediate death after 2023Q1** — 2023Q2–Q4 averaged +0.15 bps (noise). Three consecutive
   quarters of nothing.
4. **Mostly dead/negative 2024** — three of four quarters negative, including −3.78 in Q3.
5. **Suggestive but unconfirmed 2025** — Q1 +4.08 (p=0.073, 30 days) and Q2 +2.04, but Q3 flat
   and Q4 tiny sample. The yearly +2.66 is encouraging but not BH-significant.

This is the signature of a **conditional alpha tied to a specific macro/volatility regime**
(possibly the SVB/banking stress period of early 2023) rather than a durable structural edge.
When that regime ended, the edge died immediately. It did not "decay gradually" — it fell off a
cliff after Q1 2023.

### Honest revised verdict (post-granular slicing)

**Signal is real but regime-conditional and currently extinct. NO-GO for deployment.**

The 2025Q1/Q2 recovery is tantalizing but under-powered and possibly another transient regime
burst. Until a rolling regime-detector can identify *ex ante* when the edge is "on," this is
untradeable.

The "surviving FX edge = weekly+ only" conclusion **stands**. Weekly/monthly mean-reversion
([[project_fx_weekly_meanreversion_lead.md]]) remains the only demonstrated, regime-robust
retail-FX edge in this program.

### Lesson

Always slice by **calendar quarter** (or finer) before trusting a pooled t-stat. A single
anomalous quarter can carry an entire "significant" result, and a median split will mask this
completely.

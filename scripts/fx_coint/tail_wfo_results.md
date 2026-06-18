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

---

## UPDATE: Death diagnostic — why did the edge die? (IC / vol / tail-toxicity decomposition)

Running `diagnose_edge_death_pooled` on EUR/GBP/JPY 2h long q0.95: for **every WFO test
observation** (not just gated trades), compute per-quarter Spearman IC, realized vol, gross-all,
gross-top-q, and net-top-q. This distinguishes three failure modes:

1. **IC collapse** → model mapping broke → retraining MIGHT help.
2. **IC stable + vol collapse** → z-space prediction works but bps reward too small →
   retraining WON'T help.
3. **IC stable + vol stable + topq gross negative** → adverse selection in the tail →
   retraining WON'T help.

### Pooled quarterly diagnostic

| qtr | n | nTop | IC | vol | gAll | gTopQ | netTQ |
|---|---|---|---|---|---|---|---|
| 2022Q1 | 168 | 14 | **+0.122** | 14.5 | +1.46 | **+6.75** | **+6.06** |
| 2022Q2 | 780 | 70 | −0.000 | 16.8 | +0.51 | +2.82 | +2.13 |
| 2022Q3 | 792 | 90 | +0.062 | 19.5 | +0.65 | +1.39 | +0.70 |
| 2022Q4 | 780 | 161 | +0.032 | 27.8 | +0.54 | +1.66 | +0.97 |
| **2023Q1** | **777** | **81** | **+0.020** | **19.7** | **+0.78** | **+5.77** | **+5.08** |
| 2023Q2 | 780 | 32 | −0.034 | 13.2 | +0.85 | +1.73 | +1.04 |
| 2023Q3 | 780 | 40 | +0.024 | 13.4 | −0.13 | −0.39 | −1.08 |
| 2023Q4 | 765 | 56 | −0.034 | 16.0 | +0.34 | +0.48 | −0.21 |
| 2024Q1 | 768 | 10 | +0.008 | 12.6 | +0.86 | +6.03 | +5.34 |
| 2024Q2 | 780 | 28 | +0.009 | 12.6 | +0.27 | −0.08 | −0.77 |
| 2024Q3 | 789 | 50 | −0.029 | 13.4 | −0.36 | −1.82 | −2.51 |
| **2024Q4** | **780** | **29** | **+0.137** | **14.3** | **−0.67** | **+0.43** | **−0.26** |
| 2025Q1 | 756 | 45 | +0.003 | 16.1 | +1.11 | +4.23 | +3.54 |
| 2025Q2 | 780 | 50 | +0.043 | 17.6 | +0.12 | +3.48 | +2.79 |
| 2025Q3 | 789 | 36 | +0.015 | 12.4 | +0.20 | +2.00 | +1.31 |
| 2025Q4 | 780 | 7 | +0.045 | 10.8 | +0.51 | +3.09 | +2.40 |
| 2026Q1 | 756 | 27 | +0.040 | 14.2 | +0.42 | −0.86 | −1.55 |
| 2026Q2 | 420 | 6 | +0.116 | 9.2 | −0.13 | +1.33 | +0.63 |

### The verdict: retraining is NOT the answer

Three facts from the diagnostic kill the retraining hypothesis:

**1. IC is not dead — sometimes it's excellent in "bad" quarters.**
- 2024Q4 has the **highest IC in the entire sample** (+0.137) but net is **negative** (−0.26).
- 2026Q2: IC +0.116, net +0.63 (positive but tiny).
- Even 2025Q2 (IC +0.043) produces +2.79 net.

The model is STILL ranking. The mapping from features to target has **not** broken.

**2. The expected IC-to-payoff relationship collapsed at the tail.**
With IC=+0.137 and vol=14.3 (2024Q4), the theoretical top-5% lift from a monotonic rank
relationship is ~3.2 bps. Observed: **0.43 bps** — a 7× shortfall. The model ranks correctly
but the *extreme* tail (where the strategy lives) is disproportionately unrewarding. This is
**tail toxicity**: the top-ranked trades behave worse than the rank-relationship predicts.

**3. WFO already re-trains every fold.** The model is already adapting to progressively newer
data. If retraining on recent data helped, the later folds would show it. They don't.

### What actually killed the edge

The edge died because the **payoff distribution became concave**: the model still predicts
direction in the middle of the distribution, but the extreme tail (top 5%) is where it is
most wrong. Possible mechanisms:
- **Adverse selection at extreme confidence:** high predicted scores coincide with liquidity
events, fading momentum, or crowded positioning.
- **Regime-dependent convexity:** the momentum signal worked in trending/volatile regimes
(2022, 2023Q1) but generates mean-reversion in chop (2023Q2+). The tail is where this regime
switch is most severe.
- **Feature starvation:** 5 price-only features lack regime indicators (vol regime, macro trend,
liquidity proxies) to distinguish "good momentum" from "bad momentum."

### Bottom line

Retraining the same 5-feature Ridge model on newer data **will not fix this.** The ranking
ability is intact. The problem is that the *economic content* of the ranking at the extreme
tail has evaporated. A richer model (with regime/vol/flow features) might help, but that's a
new research program, not a retraining pass.

The "surviving FX edge = weekly+ only" conclusion **stands**.

### Lessons

1. **Pooled statistics are dangerous without death diagnostics.** A median split can say "decay."
   The IC/vol/tail decomposition says "tail toxicity." These imply completely different actions.
2. **Positive IC ≠ tradeable edge.** You need monotonicity AND tail payoff. A concave
   relationship (positive in the middle, flat/reversing at extremes) is worthless for a
   tail-gated strategy.
3. **Build `diagnose_edge_death_pooled` into every WFO result.** It runs automatically and
costs nothing, but it prevents chasing ghosts.

Always slice by **calendar quarter** (or finer) before trusting a pooled t-stat. A single
anomalous quarter can carry an entire "significant" result, and a median split will mask this
completely.

---

## UPDATE: Deep diagnostic — WHY the tail stopped paying (hit / magnitude / skew / vol-conditional IC)

Running `diagnose_why_tail_died` on EUR/GBP/JPY 2h long q0.95 decomposes the failure into
four mechanisms: hit-rate vs magnitude, distribution shape, vol-conditional IC, and entry-hour
shift.

### Deep diagnostic: hit-rate, win average, loss average, skew

| qtr | nTop | hit% | winAvg | lossAvg | skew | kurt | netTQ | topHours |
|---|---|---|---|---|---|---|---|---|
| 2022Q1 | 14 | **79%** | **+9.48** | **−3.23** | +1.02 | +0.73 | **+6.06** | 18:00 |
| 2022Q2 | 70 | 57% | +9.63 | −6.26 | +0.97 | +3.93 | +2.13 | 18:00 |
| 2022Q3 | 90 | 52% | +10.13 | −8.15 | +1.88 | +9.57 | +0.70 | 18:00 |
| 2022Q4 | 161 | 55% | +16.07 | −15.70 | +0.42 | +4.08 | +0.97 | 18:00 |
| **2023Q1** | **81** | **68%** | **+12.71** | **−8.92** | +0.25 | +3.46 | **+5.08** | 18:00 |
| 2023Q2 | 32 | 56% | +7.11 | −5.19 | −0.70 | +3.33 | +1.04 | 18:00 |
| 2023Q3 | 40 | 50% | +8.07 | −8.85 | −0.71 | +3.30 | −1.08 | 18:00 |
| 2023Q4 | 56 | 45% | +9.00 | −6.40 | +1.35 | +4.76 | −0.21 | 18:00 |
| 2024Q1 | 10 | 70% | +11.10 | −5.78 | +1.23 | +2.88 | +5.34 | 18:00 |
| 2024Q2 | 28 | 50% | +10.45 | **−10.60** | +1.17 | +4.88 | −0.77 | 18:00 |
| 2024Q3 | 50 | 40% | +11.05 | −10.40 | +0.16 | +1.28 | −2.51 | 18:00 |
| **2024Q4** | **29** | **59%** | **+8.56** | **−11.08** | +0.23 | +0.10 | −0.26 | 18:00 |
| 2025Q1 | 45 | 58% | +12.59 | −7.22 | +0.98 | +3.47 | +3.54 | 18:00 |
| 2025Q2 | 50 | 64% | +11.05 | −9.98 | −0.60 | +3.96 | +2.79 | 18:00 |
| 2025Q3 | 36 | 58% | +8.90 | −7.65 | +0.28 | +2.12 | +1.31 | 18:00 |
| 2025Q4 | 7 | **86%** | +4.08 | −2.90 | +0.55 | +1.22 | +2.40 | 18:00 |
| 2026Q1 | 27 | 41% | +11.44 | −9.31 | +0.30 | +1.87 | −1.55 | 18:00 |
| 2026Q2 | 6 | 67% | +9.02 | **−14.06** | +0.54 | +0.56 | +0.63 | 16:00, 18:00 |

### What the deep diagnostic reveals: the payoff asymmetry inverted

The tail stopped paying because **win-loss asymmetry collapsed** — the mechanism is not
retraining, it is regime-dependent convexity.

**Good quarters (2022Q1, 2023Q1, 2025Q1):**
- Wins are **massive**, losses are **small**.
- 2022Q1: wins (+9.48) are **3×** losses (−3.23). With 79% hit rate, this is a blowout.
- 2023Q1: wins (+12.71) are **1.4×** losses (−8.92). Positive skew + 68% hit = strong net.
- The market was **trending** — momentum trades catch big moves and have small pullbacks.

**Bad quarters (2023Q3+, 2024, 2026Q1):**
- Wins and losses are **roughly the same size** — sometimes losses are **bigger**.
- 2024Q4: losses (−11.08) **exceed** wins (+8.56) despite 59% hit rate. Net negative.
- 2024Q2: losses (−10.60) slightly exceed wins (+10.45). Net negative.
- 2024Q3: losses (−10.40) roughly equal wins (+11.05) with only 40% hit rate. Net negative.
- The market was **choppy/mean-reverting** — momentum trades generate whipsaws: big wins AND big
  losses. You need >55% hit rate to overcome symmetric payoffs + cost, and you don't get it.

### The hit rate alone tells part of the story

| era | typical hit% | asymmetry | regime inference |
|---|---|---|---|
| 2022–early 2023 | 55–79% | wins ≫ losses | trending / volatile |
| late 2023–2024 | 40–50% | wins ≈ losses (or losses bigger) | choppy / mean-reverting |
| 2025 | 58–64% | wins > losses (moderate asymmetry) | mixed / partial recovery |
| 2026 | 41–67% | losses ≈ wins | choppy |

### Vol-conditional IC: the model ranks everywhere, but not at the right times

The `ic_by_vol` column (quintiles of |return|, i.e. realized bar vol) shows that the rank
correlation varies by volatility regime but **does not cleanly favor** any single regime:
- In good quarters, IC is sometimes highest in the middle vol quintiles.
- In bad quarters, IC is sometimes highest in high-vol or low-vol.
- There is **no reliable vol-filter** that says "only trade when vol is high" or vice versa.

This means: **the market state is not captured by realized bar volatility alone.** The regime
that matters (trend vs chop) is orthogonal to the vol quintile of the individual 2h bar.

### The entry hour never moved

`topHours = [18.0]` across virtually **every quarter** (2022Q1 through 2026Q1). The model
still identifies the same time-of-day edge. The *time* is still predictive — the *market
state at that time* stopped producing momentum continuation.

This rules out "the signal shifted to a different hour" and reinforces that the issue is
**regime, not timing**.

### The REAL answer: concave payoff from regime-dependent convexity

The tail stopped paying because the **payoff function of the momentum signal is regime-dependent:
concave in chop, convex in trend.**

In a **trending regime**, the next 2h bar after a high-confidence prediction tends to continue
the move. Wins are big; losses are small (the move pauses but doesn't sharply reverse).
Positive skew.

In a **choppy/mean-reverting regime**, the next 2h bar often reverses. Even when the model is
"right" about direction over some horizon, the 2h next-bar captures the reversal, not the
continuation. Big wins and big losses. Symmetric (or negatively skewed) payoff.

**This is not a model problem — it is a market-structure problem.** The 5-feature Ridge
model has no regime indicator to distinguish "trending 18:00" from "choppy 18:00." It sees the
same features, makes similar predictions, but the *economic mapping* from prediction to payoff
flips between convex and concave.

### Bottom line

- **Retraining will NOT fix this.** The model still ranks; the mapping is intact. The problem
  is the payoff distribution, not the coefficients.
- **Vol-filtering will NOT fix this.** Realized bar vol does not cleanly separate trend from
  chop at the regime level.
- **What WOULD help:** a regime-aware model (trend vs chop) or a regime-agnostic position-sizing
  rule (reduce size / tighten stop when the payoff asymmetry compresses). Both require new
  features or new meta-rules, not retraining the same 5-feature model.

The "surviving FX edge = weekly+ only" conclusion **stands**.

### Lesson

**Every tail-gated strategy's profitability lives or dies by payoff asymmetry, not by hit rate
alone.** Always decompose:
1. `win_avg` vs `loss_avg` — the asymmetry ratio
2. `skew` of top-q returns — positive = trend-friendly, negative = chop-toxic
3. `topHours` stability — if the hour shifts, the signal migrated; if the hour is stable, the
   regime changed
4. `ic_by_vol` — is there a vol regime where IC holds? If not, the regime is invisible to
   the model.

Build `diagnose_why_tail_died` into every WFO result. It costs nothing and prevents chasing
ghosts.

---

## UPDATE: Regime + meta-rule experiment — can we rescue the edge?

Built `add_trailing_regime_features` + `gate_trades_regime` + `gate_trades_meta` and tested
all combinations: baseline (no filters), regime-only (skew threshold), meta-only (payoff-ratio
threshold), and both together. Features are computed from PAST data only (no look-ahead).

### Pooled results (EUR/GBP/JPY 2h long q0.95)

| variant | n | meanNet | dayT | dayP | hit |
|---|---|---|---|---|---|
| baseline (no filters) | **832** | **+1.27** | **+2.78** | **0.006** ✓ | 52% |
| regime skew≥0.3 | 267 | +1.33 | +1.84 | 0.067 | 50% |
| regime skew≥0.5 | 224 | +1.21 | +1.88 | 0.063 | 49% |
| regime skew≥0.7 | 186 | +0.35 | +0.37 | 0.709 | 47% |
| meta payoff≥1.0 | 34 | +2.77 | +1.04 | 0.309 | 62% |
| meta payoff≥1.2 | 20 | +3.94 | +1.68 | 0.112 | 65% |
| meta payoff≥1.5 | 12 | +2.69 | +0.86 | 0.409 | 50% |
| regime≥0.3 + meta≥1.2 | 17 | +3.37 | +1.11 | 0.283 | 71% |
| regime≥0.5 + meta≥1.2 | 16 | **+4.64** | +1.61 | 0.131 | **75%** |
| regime≥0.3 + meta≥1.5 | 11 | +3.16 | +0.68 | 0.513 | 55% |
| regime≥0.5 + meta≥1.5 | 10 | **+5.17** | +1.11 | 0.295 | 60% |

### Per-pair breakdown (selected variants)

**EURUSD:**
- Baseline: +1.19 (n=271)
- Regime skew≥0.5: **+1.67** (n=79) — improves but N collapses
- Meta alone: noise (3–12 trades)

**GBPUSD:**
- Baseline: +0.92 (n=192)
- Regime skew≥0.5: **−0.13** (n=92) — **kills** the edge
- Meta payoff≥1.5: **+39.10** (n=1) — cherry-pick artifact, not a strategy

**USDJPY:**
- Baseline: +1.50 (n=369)
- Regime skew≥0.3: **+2.93** (n=65) — **helps**
- Regime≥0.5 + meta≥1.5: **+4.42** (n=6) — best per-trade, tiny N

### What the experiment reveals

**1. The regime filter works directionally for USDJPY but hurts GBPUSD.**
The three pairs respond differently to the same filter because their payoff asymmetries have
different sensitivities to regime. EURUSD is mixed. This means a **uniform pooled filter is
wrong** — you'd need pair-specific thresholds, which introduces more degrees of freedom.

**2. The meta-rule (payoff ratio) is too sparse to be useful.**
payoff≥1.2 leaves only 20 pooled trades across all three pairs. The per-trade mean is high
(+3.94) but the day-clustered t-stat (+1.68, p=0.112) is nowhere near significance. With
<1 trade per month, this is not a tradeable signal — it's a cherry-picker.

**3. Combined filters produce the highest per-trade mean (+5.17) but destroy statistical power.**
16–17 trades, p=0.13–0.28. The hit rate is impressive (75%) but with N=16, a single bad
day can flip the sign. This is the classic quality-vs-quantity trade-off, and quantity wins
for significance.

**4. The baseline is the ONLY variant that clears significance.**
All filtered variants have p > 0.05. The baseline p=0.006 is already marginal — it survives
a 3× Bonferroni for the q-sweep (→0.018), but it would not survive a 10-variant regime-sweep.

### The fundamental trade-off

| approach | n | per-trade mean | significance | verdict |
|---|---|---|---|---|
| Baseline (unfiltered) | 832 | +1.27 | **p=0.006** | Marginal but real |
| Regime filter | ~250 | +1.20–1.35 | p=0.06–0.07 | Better quality, no significance |
| Meta filter | ~20 | +2.7–3.9 | p=0.11–0.31 | Cherry-picking, not tradeable |
| Combined | ~15 | +3.4–5.2 | p=0.13–0.30 | Highest per-trade, no power |

**You cannot have both high-conviction filtering AND statistical power with this sample size.**

If you had 10× the history, regime filtering would likely be the right move. With the current
sample, the baseline is the only variant that clears the significance bar — and even that is
NO-GO for deployment because of the era-split decay proven earlier.

### Pair-specific observation: USDJPY is the only pair where regime detection genuinely helps

USDJPY responds strongly to skew filtering (+2.93 at skew≥0.3 vs +1.50 baseline), and combined
regime+meta produces the highest per-trade mean (+4.42). If you were to trade this signal on a
single pair, USDJPY with skew≥0.3 would be the only honest choice — but it's still
under-powered (n=65 is too few for day-clustered significance).

### Bottom line

**Regime detection and meta-rules are directionally correct but sample-size-starved.**

The diagnosis was right (payoff asymmetry inversion is the mechanism), but the prescription
(regime filtering) is not viable without 3–5× more data. The edge is real when the regime is
right, but identifying the regime *ex ante* with trailing features costs too many observations
to remain significant.

The "surviving FX edge = weekly+ only" conclusion **still stands**.

### Lesson

**Any filter that drops >60% of trades will likely kill significance unless you have 5×+
the data.** Before building a regime filter, compute the N trade-off explicitly:

```
required_n = (z_critical * std / min_detectable_mean) ** 2
```

If filtering drops you below required_n, the filter is not deployable regardless of how much
it improves per-trade mean. Always test the filtered result with the SAME significance
standard (day-clustered t) as the baseline.

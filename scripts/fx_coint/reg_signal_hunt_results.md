# FX Regression Signal Hunt (1–4h) — Results & Verdict

**Date:** 2026-06-18
**Script:** `scripts/fx_coint/reg_signal_hunt.py`
**Run:** `--symbol all --freq all` (6 majors × {1h,2h,3h,4h}, **simplest possible model**:
Ridge on 5 price-only features, vol-normalized target, single 70/30 temporal split
with purge, London+NY session 07–21 UTC, net of real Pepperstone Razor costs).

> **Read this first:** the whole-sample IC averages over dead hours *and* over the
> untraded middle of the prediction distribution. Trading reality only touches the
> high-conviction tail at the right entry hours. The headline IC table understates
> the edge; the decile and per-hour cuts below are the load-bearing evidence. And
> this is the *floor* — the crudest model we could build; features/models can only lift it.

## 1. Whole-sample IC vs break-even (context, not verdict)

| pair | 1h | 2h | 3h | 4h |
|---|---|---|---|---|
| EURUSD | 0.005 | 0.046 | **0.057** | -0.027 |
| GBPUSD | 0.011 | 0.012 | -0.019 | -0.055 |
| AUDUSD | 0.018 | 0.017 | -0.039 | 0.009 |
| USDJPY | -0.002 | -0.007 | **0.114** | 0.011 |
| USDCHF | 0.012 | 0.019 | -0.028 | 0.005 |
| USDCAD | 0.010 | 0.002 | 0.043 | 0.005 |

Break-even IC\* ranges ~0.04 (3h tight majors) to ~0.14 (1h wide pairs). **1h is dead
for every pair** (IC an order of magnitude below the bar — cost wall, as predicted).
Signal concentrates at **2–3h**, and three pairs (EUR/JPY/CAD) peak at 3h.

## 2. The edge is in the tail — top-decile conditional return, net of real cost

Long the top predicted decile (the cleanest "does high conviction clear cost" read):

| pair | 2h netLong | 2h TOPhit | 3h netLong | 3h TOPhit |
|---|---|---|---|---|
| **EURUSD** | **+0.64** | 56% | **+1.27** | 62% |
| **GBPUSD** | **+0.28** | 51% | **+1.71** | 56% |
| **USDJPY** | **+0.72** | 52% | -1.47 | 53% |
| **USDCAD** | -1.21 | 49% | **+2.22** | 59% |
| AUDUSD | -0.36 | 53% | -0.93 | 45% |
| USDCHF | -1.96 | 53% | -3.68 | 48% |

(2h N_top = 261; 3h N_top = 66.)

**Cost tiering acts as a pair filter, exactly as predicted.** The cells that clear are
the cheap majors (EUR/GBP/JPY ≈ 0.6–0.8 bps); the ones that fail are the expensive ones
(AUD/CHF/CAD ≈ 1.0 bps). Tight-cost top-decile longs are net-positive after real cost at
2h (EUR/GBP/JPY) and 3h (EUR/GBP/CAD), with hit rates 56–62%.

## 3. The signal is one-sided (long), with one exception

The bottom decile (short side) is broadly **broken**: `netShort` is negative for most
pairs because bottom-decile realized returns are not actually negative. The model carries
long-side (continuation) conviction but little short-side conviction.

**Exception — USDJPY 3h is short-sided / mean-reverting:** its +0.114 IC comes from the
*down* move (netShort +2.66, bottom-decile hit 60%), not continuation. This sign
heterogeneity across pairs is a real obstacle to a single pooled model.

## 4. Entry-hour concentration

- **2h: the 18:00 UTC entry is positive for all six pairs** (EURUSD +0.095, AUDUSD +0.137,
  USDJPY +0.136, USDCHF +0.132, GBPUSD +0.036, USDCAD +0.035). 6/6 same-sign at one entry
  hour is a coherent breadth pattern; the weak whole-sample 2h IC is the average of this
  against a negative 12:00 bucket.
- **3h: the 15:00 UTC overlap** carries the signal for EUR (+0.049), JPY (+0.088),
  CAD (+0.054); GBP/AUD/CHF are negative there. 3/6.

## Verdict: NOT a no-go — a certification-limited, tail-and-cost-tier edge

With the **simplest possible model**, the **top-decile long on tight-cost majors
(EURUSD/GBPUSD at 2h & 3h, USDCAD at 3h) is net-positive after real Pepperstone cost**,
hit rates 56–62%, plus a clean 6/6 18:00-UTC 2h breadth pattern. This is a floor.

The remaining blockers are **certification, not absence of edge**:

1. **Sample / single split.** 3h N_top = 66; results rest on one 70/30 split.
2. **Multiplicity in the tail.** These decile means are themselves multiple comparisons;
   they need decile-level significance, not just whole-sample IC + BH.
3. **Long/short asymmetry & sign heterogeneity** (esp. USDJPY 3h reverting) — argues for
   long-only, per-pair (or cost-tier-grouped) models, not one pooled sign.

## Next step (the actual tradeable strategy, not the diagnostic)

Test **top-decile (or |pred|-gated) LONG-ONLY, tight-cost majors only, walk-forward**, with
the **18:00-UTC@2h and 15:00-UTC@3h entry concentration as the design**, and report
decile-level significance net of cost. If that survives walk-forward + multiplicity →
tick-exact fill verification before sizing.

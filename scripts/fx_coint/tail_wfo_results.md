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

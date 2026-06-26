# FX diversification: cross-sectional reversion complements the 1000-tick FFD triple-barrier edge

**Date:** 2026-06-26  **Branch:** `feat/fx-shortterm-55`

## Problem
Every FX edge built to date — st55 ~33h directional, 2–3d fade, weekly mean-reversion,
and the 1000-tick fractional-diff triple-barrier (TB) reversion — is fundamentally the
**same USD-directional reversion factor**. They co-lose in the chop years (2022/2024/2026),
so stacking them by *timeframe* does not reduce portfolio drawdown. Stops don't help
(reversion is path-dependent). Need a genuinely **orthogonal driver**.

## Edge added: cross-sectional dollar-neutral reversion (`xs_reversion.py`)
1. Convert the 6 majors to currency-vs-USD daily returns.
2. **Cross-sectionally demean each day** → removes the common USD factor, leaving the
   currency-specific residual.
3. Fade the rolling-L residual with a **dollar-neutral, gross-1** book
   (`w = -zscore(resid_signal)`, shifted 1 day = causal). PnL = what a market-neutral
   long-laggard / short-leader book earns, minus turnover cost.

Structurally orthogonal to USD *direction* by construction.

**Standalone (2018–2026, full turnover cost):** modest but real and cost-robust at
longer lookback — L=20: Sharpe 0.23, **8/9 positive years**, max DD −660 bps
(vs the directional weekly's −4237). Short L (3) had higher Sharpe but was largely
turnover illusion.

## The combination (`xs_plus_tbreal_portfolio.py`)
Canonical TB book = 1000-tick `ffd_zvol20` (fractional-diff) fade, triple-barrier
first-touch payoff, top-decile magnitude, non-overlapping, walk-forward (`pnl_walkforward.py`).
50/50 unit-vol risk blend with XS reversion (N_TB=50):

| book (unit-vol) | Sharpe | max DD | Calmar | pos years |
|---|---|---|---|---|
| TB (1000-tick FFD triple-barrier) | 0.70 | −27.8 | 0.40 | 6/9 |
| XS reversion | 0.22 | −29.4 | 0.12 | 8/9 |
| **Combined 50/50** | **0.62** | **−16.7** | **0.44** | **8/9** |

- Correlation TB vs XS = **+0.10** (low; largely independent).
- **Max drawdown ~40% shallower** (−27.8 → −16.7) — the headline win for a DD-constrained book.
- Positive years **6/9 → 8/9**; XS rescues TB's down years (2024 −3.0 → +1.9, 2019 −0.3 → +3.1).
- Modest Sharpe give-up (0.70 → 0.62) for the large drawdown cut.

## Verdict
Cross-sectional dollar-neutral reversion is the **first structurally-orthogonal FX edge**
and a genuine diversifier for the 1000-tick FFD triple-barrier book: it cuts drawdown and
broadens year coverage at a small Sharpe cost. Correct trade for the <10% max-DD / $100k
objective.

## Caveats / next
- +0.10 correlation is not negative — both are reversion; real but imperfect hedge.
- XS total is somewhat carried by 2025 (+578 bps at L=3) — check concentration.
- Unit-vol blend; translate to %-return only after proper sizing to the 10% DD budget.
- Next: add more orthogonal legs (cross-sectional **momentum**), then optimize the blend
  weights for max Calmar and report the sized-to-10%-DD annual return.

Scripts: `scripts/fx_coint/xs_reversion.py`, `xs_plus_tbreal_portfolio.py`
(and `xs_plus_tb_portfolio.py` = the earlier wrong-book diagnostic, kept for the record).

# Retail FX Risk-Premia Exploration — Findings (Negative, with one gross-real effect)

**Date:** 2026-06-06
**Branch:** `worktree-era-fixing-premium`
**Status:** Complete. No tradeable edge found in the 6 USD-major universe at retail cost.
**Data:** tick-velocity 1000-tick bars, 6 USD majors, 2018–2026. Split: train 2018–23,
val 2024, holdout 2025–26 (holdout read once, per pre-registered config).

## Purpose

After tick-scalping and intraday cross-sectional baskets both failed, test whether a
documented **risk premium** — a small, structural, patience-not-speed return — survives
retail transaction costs in our data. Two hypotheses: (1) intraday fixing/seasonality
premium (Krohn–Mueller–Whelan, JF 2024); (2) time-series momentum (Moskowitz–Ooi–Pedersen).

## Headline

**No hypothesis produced a statistically significant, cost-surviving edge.** The intraday
USD seasonality is **real in gross** but smaller than cost; time-series momentum has **no
gross premium** in this sample. The binding constraints are the same as before: retail cost
(~5.7 pips round-trip on the 6-leg basket, ~0.95/leg) and lack of breadth.

## Hypothesis 1 — Intraday fixing / seasonality premium

**Method.** Timed USD-basket trade over an intraday window [enter→exit] UTC, once daily,
equal-weight 6 majors. Long-USD P&L = Σ usd_sign·Δmid/pip; cost = Σ cost_est_pips (one round
trip). Decomposed gross vs cost vs significance.

**Gross effect is real.** A genuine intraday USD rotation exists: USD strengthens during the
US session and is flat/weak overnight (a seasonality, NOT a trend — the session sign flips):

| window (UTC) | long-USD gross | cost | net_long | net_short |
|---|---|---|---|---|
| 00→06 | −1.51 | 5.72 | −7.23 | −4.21 |
| 06→10 | +3.16 | 5.72 | −2.55 | −8.88 |
| 10→16 | +5.75 | 5.70 | **+0.05** | −11.44 |
| 16→22 | −4.53 | 5.77 | −10.30 | −1.24 |
| 21→23 | −7.24 | 5.71 | −12.96 | **+1.53** |
(pips/day, train+val 2018–2024)

**But it does not survive cost.** Only two cells are net-positive, both marginal:
- 10→16 long-USD: +0.05 (breakeven).
- 21→23 short-USD: +1.53/day in-sample — but **t=0.85, 51% positive months** (coin flip);
  holdout +3.49 but **t=0.35, 40% positive months**. The positive mean is a few large
  months, not consistency. Also the thinnest-liquidity window (n=511 ≈ ⅓ of days; cost
  realism most suspect). Verdict: noise, not edge.

**Process note (recorded so it isn't repeated):** an early version negated `net = gross −
cost` to flip trade direction, which also flips the cost sign (adds cost instead of
subtracting). That produced a spurious "+7.59 pips/day, 7/7 years positive" before the
gross-vs-cost control exposed it. Always decompose gross and cost separately; a positive net
mean with ~50% positive months is noise.

## Hypothesis 2 — Time-series momentum (low turnover; escapes the cost wall)

**Method.** Monthly close per pair; position = sign(trailing k-month return), held next
month; equal-weight 6-pair portfolio. Turnover ~monthly ⇒ cost negligible per day.

**No gross premium** (before cost):

| k (months) | train+val ann | t | holdout ann | t |
|---|---|---|---|---|
| 3 | −1.4% | −0.70 | +0.1% | +0.03 |
| 6 | −0.7% | −0.39 | −6.4% | −1.41 |
| 12 | −0.7% | −0.33 | +1.2% | +0.32 |

Flat-to-negative gross, |t|<1.5, ~50% hit rate. Consistent with the documented post-2010
decay of FX trend/carry premia. Cost is irrelevant — there is no gross edge to harvest.

## Unifying conclusion (whole research arc)

| Approach | Result | Binding constraint |
|---|---|---|
| Directional tick scalping | FAIL | coin-flip gross; cost |
| Intraday cross-sectional basket | FAIL | no breadth (6 correlated USD pairs); cost |
| Intraday fixing/seasonality | gross real, FAIL net | cost (~1 pip/leg) > gross seasonality |
| Time-series momentum | FAIL (gross) | premium decayed to ~0 in sample |

In the 6 USD-major universe at retail cost over 2018–2026, the structural premia that exist
are smaller than transaction cost, and the cost-escaping premium (TSMOM) has decayed to zero
gross. This empirically confirms the a-priori caution: *whether a tiny edge survives spread
at the realized turnover is the whole ballgame, and here it does not.*

## What would change the answer (future directions)

1. **Lower cost** than retail Dukascopy (the seasonality 21→23 short-USD gross +7.24 beats a
   ~5.7-pip basket cost only marginally; at half the cost it would clear comfortably).
2. **Breadth** for cross-sectional: onboard crosses + EM (EURGBP, EURJPY, … and beyond),
   which requires generalising USD-alignment to non-USD-quoted pairs.
3. **Data the universe lacks**: rate differentials for a genuine carry book (the one FX
   premium with the strongest long-run evidence), which intraday price data cannot supply.

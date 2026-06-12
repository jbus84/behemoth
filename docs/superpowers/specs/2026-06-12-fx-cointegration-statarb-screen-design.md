# FX Cointegration Stat-Arb — Modelling-Readiness Screen

**Date:** 2026-06-12
**Status:** Design — approved direction, pending spec review
**Type:** Research feasibility (go/no-go), not a build

## Purpose

Decide whether the *stage is set* for modelling cross-FX stat-arb — i.e. whether
genuine, stable, mean-reverting cointegration structure exists across our majors
with reversion amplitude in reach of trading cost. This is a **cheap screen that
fails fast**. We do **not** require any net-positive edge from a baseline: extracting
net edge from the structure is the model's job (TimeBridge, arXiv 2410.04442, whose
Cointegrated Attention is purpose-built for this). The screen only answers: is there
something worth modelling, or is this another cost-wall null?

This continues a line of FX edge research. Prior findings that shape it:
- Every retail-FX approach so far has died on the cost wall except weekly/monthly
  mean-reversion (the one surviving edge).
- FX predictability is wall-clock-specific (lives on time bars, collapses on tick bars).
- Discipline: decompose gross / cost / significance; positive-month %; ~50% = noise;
  BH-FDR / multiplicity correction; guard against look-ahead.

## Data

- 6 USD majors: EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD.
- 2018-01 → 2026-05 (~8.4 yrs), stored as 100/1000/2000-tick bars with bid/ask,
  per-bar spread, and intra-bar microstructure. `data/tick_bars/*.parquet`.
- **Real spread data for the 6 pairs** ⇒ cost is measured, not assumed.
- No raw ticks (we resample from 100-tick bars) and **no cross-rate spread data**.

## Scope decisions (settled)

- **Endpoint:** go/no-go feasibility first. TimeBridge only if the screen says the stage is set.
- **Timeframes:** daily (primary), hourly (secondary), weekly (upper-amplitude bound).
  Tick bars excluded (prior work shows reversion structure is a wall-clock phenomenon).
- **Universe:** (1) pairwise Engle-Granger residuals on the 6 USD pairs;
  (2) multivariate Johansen + per-currency strength-basket residuals on the 6;
  (3) synthetic crosses (7-currency / 21-pair complex) built by log-additivity.
- **Target variable:** the **spread residual**, not raw pair returns. (Raw-return
  prediction is a different, non-stat-arb bet — out of scope.)
- **Cost:** for the 6 real pairs, actual per-bar median spread; report the
  amplitude-vs-cost ratio across a **markup sweep** (+0, +0.3, +0.6, +1.0 pip/leg,
  round-trip = 2 legs). Synthetic crosses: cost proxied as sum of the two USD legs
  (conservative upper bound) — their true go/no-go needs real cross spreads, flagged.

## Pipeline

### Stage 0 — Bar construction
Resample 100-tick bars → daily / hourly / weekly OHLC + per-bar median spread; mid from
bid/ask. Build synthetic cross log-prices via additivity (`log EURGBP = log EURUSD −
log GBPUSD`). Output aligned log-price panels per timeframe. Resampling note: close/mean
are exact; OHLC extremes carry a small downward bias — acceptable for residual/spread work.

### Stage 1 — Cointegration screen (log-prices; walk-forward, rolling ~1–2 yr train)
- **Pairwise Engle-Granger** both directions → ADF on the **residual** (not levels);
  record hedge ratio β, ADF statistic, half-life.
- **Johansen** on the 6 jointly + per-currency strength factor (each pair's deviation
  from its implied basket value).
- **Stability is a first-class output:** % of walk-forward windows the relationship
  holds + structural-break test (Gregory-Hansen / CUSUM). In-sample-only cointegration
  is rejected.
- **BH-FDR** across every relationship tested (kills the multiple-testing mirage).

### Stage 2 — Reversion & amplitude measurement (pure measurement, no trading)
For each surviving (stable, FDR-passing) spread, fit OU on the train residual; measure **OOS**:
- θ (mean-reversion speed) and half-life → feeds condition **B**.
- Whether deviations are followed by reversion *on average* OOS (significant, with a
  minimum number of reversion events for statistical weight) → feeds **B**.
- Gross reversion amplitude captured per round-trip vs round-trip cost (the markup
  sweep) → the **amplitude-vs-cost ratio**, feeds condition **C**.

No z-band trading, no net-PnL gate. OU is a measurement instrument only.

### Stage 3 — Modelling-readiness gate (rule fixed before running)
The stage is set for modelling iff **all three** hold for at least one spread:

- **(A) Structure exists** — genuine cointegration (not USD common-factor), stable
  across walk-forward windows, survives BH-FDR.
- **(B) Reversion exists** — residual genuinely mean-reverts on a usable horizon:
  significant OU speed θ / finite, sensible half-life, deviations followed by reversion
  on average OOS. No timing/predictability claim — that is the model's job.
- **(C) Amplitude reachable** — gross reversion amplitude per round-trip ≥ round-trip
  cost (or within a defined multiple), read off the markup sweep. Model-proof: a
  forecaster can improve timing/selection/regime but cannot make amplitude exceed cost.

Outcome:
- **≥1 spread passes A+B+C** → escalate to Stage 4 (build TimeBridge).
- **None pass** → documented **NO-GO** with the precise killing number (e.g. "structure
  real and reverting, but amplitude is X× below cost at every markup"). Model-proof null.

### Stage 4 — TimeBridge (conditional; only if Stage 3 says the stage is set)
Port TimeBridge; forecast the residual path h-ahead (Cointegrated Attention exploits the
long-run equilibria, Integrated Attention soaks up short-term non-stationarity); trade
forecast-vs-cost-band. Benchmark **strictly against an OU/z-score baseline OOS net of
cost**; ships only if it beats that baseline after cost + FDR. (Detailed Stage-4 design
is deferred until Stage 3 greenlights it.)

## Look-ahead discipline (throughout)
Walk-forward re-estimation only; no normalization peeking; purge/embargo gap between
train and OOS; residuals computed only from past-estimated β; significance via
block-bootstrap / non-overlapping samples (hourly autocorrelation ⇒ small effective N).

## Known risks / honest priors
- **Most likely outcome is NO-GO on amplitude (C).** Majors are liquid; genuine
  cointegration is sparse and what exists is low-amplitude vs a doubled two-leg cost.
- **USD common-factor mirage (A).** USDxxx pairs comove via the shared USD leg — a
  common trend, not a stationary spread. Always test the residual, never levels.
- **Synthetic-cross cost is an assumption**, not measured — their verdict is provisional
  until real cross spreads are obtained.
- **Cointegration is non-stationary** (regime breaks: SNB 2015, COVID, rate cycles) —
  hence stability/structural-break testing is part of the gate, not an afterthought.

## Out of scope
Raw-return forecasting; tick-bar models; live execution/order-routing; the full Stage-4
TimeBridge design (deferred behind the Stage-3 gate).

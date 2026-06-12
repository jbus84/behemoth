# FX Cointegration Stat-Arb — Screen Verdict

**Date:** 2026-06-12
**Result: NO-GO — the stage is not set for modelling.**
**Killed at condition A (stable cointegration), NOT the cost wall.**

## What was tested
The full 7-currency / 21-instrument complex (6 USD majors + 15 synthetic crosses),
all C(21,2) = **210 pairwise Engle-Granger spreads**, on **daily, hourly, and weekly**
bars over 2018-01 → 2026-05. Each spread judged look-ahead-safe on walk-forward OOS
slices (β + de-meaning from train only) against three conditions:

- **A — structure exists:** OOS-stationary in ≥60% of walk-forward windows **and** survives BH-FDR.
- **B — reversion exists:** finite sensible OU half-life + OOS reversion over ≥100 events.
- **C — amplitude reachable:** reversion amplitude vs a round-trip cost markup sweep (0 / 0.3 / 0.6 / 1.0 pip/leg), as a floor (close-to-close) / ceiling (intrabar) band.

Spec: `docs/superpowers/specs/2026-06-12-fx-cointegration-statarb-screen-design.md`.

## Result (identical conclusion on every timeframe)

| Timeframe | Pairs | WF windows | Best fraction_stationary | #(≥0.60) | FDR survivors | SET | EXEC-GATED | amplitude ceiling ≥ cost |
|-----------|-------|-----------|--------------------------|----------|---------------|-----|-----------|--------------------------|
| Daily     | 210   | ~7        | 0.43 (3/7)               | 0        | 0             | 0   | 0         | 210 / 210 |
| Hourly    | 210   | ~7        | 0.29 (2/7)               | 0        | 0             | 0   | 0         | 210 / 210 |
| Weekly    | 210   | ~6        | 0.50 (3/6)               | 0        | 0             | 0   | 0         | 210 / 210 |

## The decomposition is the point

**Cost is not the problem.** The amplitude *ceiling* exceeds round-trip cost for every
one of the 210 spreads on every timeframe (median ceiling ≈ 0.006 vs cost ≈ 0.00018 on
daily — roughly **33× cost**). This is the first FX approach in this research line where
the cost wall is comfortably cleared.

**Structure is the problem.** No spread is OOS-stationary in even 60% of walk-forward
windows (best case 3 of 7). BH-FDR rejects all 210. The large amplitude is precisely what
a *non-stationary, wandering* spread produces — big excursions that do not reliably revert
out-of-sample. A forecaster cannot exploit an equilibrium that isn't there OOS, so the
ample amplitude is not harvestable.

This is a **model-proof NO-GO**: not "naive bands lost money" (which a model might fix) but
"the cointegration relationship is not stable out-of-sample" (which no model can manufacture).

## Pipeline is validated, not dead
The screen's unit tests include a synthetically-cointegrated pair that the same code
correctly flags as OOS-stationary (fraction_stationary > 0.5). The all-NO-GO outcome is a
property of the FX majors, not a broken detector.

## Caveats
- Synthetic-cross spreads carry *assumed* cost (sum of USD-leg spreads); they fail at
  condition A regardless, so cost is moot for them.
- Walk-forward OOS windows are ~1 year (daily/hourly); a relationship stationary only on
  shorter sub-windows would be rejected — by design (we want durable structure).
- TimeBridge (the multivariate forecaster this screen was meant to gate) is **not justified**:
  its cointegrated-attention has no stable cointegration to model here.

## Recommendation
Do not proceed to the TimeBridge build for spot-major / cross stat-arb. If revisiting,
the productive direction is not a better model but a different *structure* source —
e.g. genuinely cointegrated instruments (same-underlying futures/ETF pairs, term-structure
legs) rather than the spot FX complex, where the prior research already shows the only
durable edge is longer-horizon (weekly/monthly) mean-reversion, not pairwise cointegration.

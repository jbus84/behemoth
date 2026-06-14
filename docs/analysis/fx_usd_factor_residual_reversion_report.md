# Hourly USD-Factor Residual Mean-Reversion

**Status:** Research probe — first FX intraday avenue with a *real, temporally-persistent* gross edge. Tradeable verdict is **execution-cost gated**, NOT predictability gated.

**Scripts:**
- `scripts/fx_coint/usd_factor_residual_probe.py` — factor construction, reversion test, XS book, session/spread sweep.
- `scripts/fx_coint/usd_factor_move_distribution.py` — move-size distribution, conditional reversion by dislocation bucket, break-even spread, per-year stability.

**Data:** 6 USD majors (EURUSD/GBPUSD/AUDUSD/USDJPY/USDCHF/USDCAD), tick bars resampled to hourly mid closes, 2018-01 → 2026-05 (46,650 aligned hours). Look-ahead guarded: factor = equal-weighted (no estimated beta), signal at `t`, forward return `t→t+1`, per-pair spread as cost.

## Findings

### 1. The USD factor is real and "known"
- PC1 explains **56.4%** of hourly oriented-return variance.
- `corr(equal-weighted dollar factor, PC1) = 0.997` → the EW factor *is* PC1; no estimation needed.

### 2. Removing the factor triples the reversion signal
Pooled OLS slope of residual `t+h` on residual `t` (negative = reversion):

| | h=1 | half-life |
|---|---|---|
| Raw oriented return | corr −0.016 (t −8.7) | — |
| **Residual (factor removed)** | **corr −0.058 (t −30.8)** | ~1 hour |

The residual — not the factor — is the predictable object. Predicting the factor is irrelevant (it is *removed*, not traded).

### 3. The un-selective book is sub-cost; the tail is not
Every-hour dollar-neutral XS book: gross **+0.52 bps/hr** (t +21, 99% positive months) but net **−0.63 bps/hr**. Dead levers: holding longer (half-life 1h), session/spread-timing (every UTC hour net-negative), tight-pairs-only.

**But conditioning on dislocation size works.** Residual moves are fat-tailed (median 3.5 bps, p99 26 bps, max 300 bps). EURUSD, conditioned on the dislocation magnitude:

| Subset | n | Gross capture | Net @0.33 (ECN) | Win% |
|---|---|---|---|---|
| Top decile (\|s\|≥8.3 bps) | ~4,665 | +0.76 bps | **+0.42** | 56 |
| Top 1% (\|s\|≥18 bps) | ~467 | +1.24 bps | **+0.81** | 55 |

**Break-even spread = 0.76 bps round-trip.**

### 4. Temporally persistent — not a single-crisis mirage
EURUSD top-decile gross capture is **positive in all 9 years** (2018–2026); weakest is 2020 (+0.09, COVID — large moves that were information, not noise). Net is positive 7/9 years at ECN spread (0.33), negative 7/9 years at retail spread (1.5).

## Verdict

A **real, persistent, selective edge (~0.4 bps/trade net)** viable **only at sub-0.76 bps EURUSD round-trip execution** (ECN/institutional). At retail/IG spreads (~1.2–1.8 bps) it is net-negative. The binding constraint is execution **access**, not signal quality or robustness.

**A better model will not push the *hourly* version past the cost wall:** the reversion fuel is bounded (corr −0.058), tighter selection shrinks the sample toward overfit, and the tail carries adverse selection (2020). Model capacity converts to P&L only where cost is *not* the binding constraint.

## Open / next

1. **Tick-exact fills (decisive):** measured capture uses close-to-close mid, but entries are *into* 18–37 bps moves — real fills are worse, and the ECN margin is only ~0.43 bps. A 0.2–0.4 bps adverse slip erases it.
2. **Lower-frequency port:** apply the same factor-residual decomposition at **daily/weekly**, where retail cost is negligible vs move size and a better model translates directly into P&L. This is also where the only other surviving FX edge lives.

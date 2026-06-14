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

## Cost refinement: raw-spread + commission broker (Pepperstone Razor)

Retail spread-betting (~1.2–1.8 bps RT) kills it, but a raw-spread + commission
account changes the floor. Pepperstone Razor ≈ **$3.5/side ≈ 0.3 pip/side ≈
~0.6–0.7 bps round-trip commission** (fixed) + near-zero raw spread. Commission
is a *flat tax per trade*, so the strategy must select trades whose gross beats it.

EURUSD gross capture by dislocation **size band** vs a 0.65 bps commission floor:

| \|s\| band (bps) | n | Gross | Win% | Net@0.65 |
|---|---|---|---|---|
| 0–2 | 18,111 | +0.16 | 52 | −0.49 |
| 2–4 | 12,516 | +0.45 | 55 | −0.20 |
| 4–6 | 7,216 | +0.60 | 56 | −0.05 |
| **6–8** | **3,770** | **+0.89** | **58** | **+0.24** |
| **8–12** | **3,320** | **+0.83** | **57** | **+0.18** |
| 12–18 | 1,241 | +0.32 | 54 | −0.33 |
| 18–30 | 385 | +1.42 | 56 | +0.77 |
| 30+ | 89 | +0.52 | **49** | −0.13 |

Two structural facts:
- **Small dislocations (<6 bps) can't clear a fixed commission** — gross < tax, win ~52% (coin-flip).
- **The extreme tail (30+ bps) does NOT revert** — win 49%, those are *information* moves (cf. 2020). The "top-1%" profit came from the 18–30 band, not the genuinely-huge candles.
- **Sweet spot = moderate 6–12 bps dislocations:** net-positive at commission, best win rate (57–58%), ~7,000-trade sample, and (being ordinary moves not news blowouts) far more benign fills.

Refined verdict: the tradeable target is the **6–12 bps band at commission-based execution**, NOT the rare huge-move tail. Because cost is now a fixed floor rather than a hard wall, **model capacity (selecting which moderate dislocations revert) converts directly to P&L** — modeling is justified here in a way it is not at spread-betting cost.

## Open / next

1. **Tick-exact fills (decisive):** capture uses close-to-close mid. Now testing the **6–12 bps band** (benign, non-event moves) rather than the 18–37 bps tail, so fills should be far closer to mid — but still the margin-deciding test.
2. **Multi-pair breadth:** apply 6–12 bps band selection across all 6 majors (similar commission each) to smooth year-to-year variance — now valuable because the binding constraint shifted from cost to sample/robustness.
3. **Lower-frequency port:** same decomposition at **daily/weekly**, where cost is negligible vs move size and a better model translates directly into P&L.

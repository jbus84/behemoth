# FX Regression Signal Hunt (1–4h) — Design

**Date:** 2026-06-18
**Status:** Approved (design), pending implementation plan
**Script (target):** `scripts/fx_coint/reg_signal_hunt.py`

## Purpose

A clean, from-scratch hunt for a **regression** signal predicting 1/2/3/4h forward
FX returns on the 6 majors, evaluated against the **break-even IC** implied by real
Pepperstone Razor costs and London/NY session volatility. Strips the existing
`fx_ic_diagnose.py` harness to a minimal price-only model and bolts the cost
economics onto the front so go/no-go is read directly off whether realized OOS IC
clears its cost bar.

## Background / what we already know

- Surviving FX edge to date is **weekly+ only**; all intraday/scalping approaches die
  at the retail cost wall. See memory: `project_fx_directional_timebar_costwall`,
  `project_fx_hourly_nextbar_direction`, `project_retail_fx_edge_cost_wall`.
- **Never resample tick-count bars into time bars** (`project_fx_usd_factor_residual_reversion`).
  The 1-min flow bars used here are genuine time bars, so resampling 1m→{1,2,3,4}h is safe.
- **Flow features were NO-GO at high power** (`project_fx_hourly_nextbar_direction`):
  flow adds nothing over price under breadth. Excluded from v1.
- Cost/IC math (this session): break-even `IC* = c / σ_h`. With real Pepperstone
  Razor costs ($3/side commission + avg spread) round-trip `c` ≈ 0.64 (EURUSD),
  0.63 (GBPUSD), 0.80 (USDJPY), 0.97 (USDCAD), 1.05 (USDCHF), 1.06 (AUDUSD) bps.
  Full London+NY (07–21 UTC) vol boost ~1.25×. Resulting break-even IC for a 2–3h
  hold on tight majors ≈ 0.029–0.036 — the first intraday band inside the
  achievable IC ceiling (~0.03–0.05).
- Achievable, OOS-stable FX IC tops out ~0.02–0.05; prior hourly work found ~0.02.
  So this is a marginal hunt: the threshold and the ceiling barely cross.

## Data & bars

- Source: `data/tick_bars/{sym}_1m_flow.parquet` for the 6 majors
  (EURUSD, GBPUSD, AUDUSD, USDJPY, USDCHF, USDCAD). Genuine 1-min time bars.
- Resample 1m → **1h, 2h, 3h, 4h** time bars: last mid/bid/ask, summed n_ticks,
  realized vol = std of 1-min log-returns (bps), mean relative spread (bps).
- **Contiguity guard:** drop bars spanning data gaps (reuse the `contig` mask:
  consecutive timestamps must differ by exactly the bar width).
- **Session filter:** keep only bars whose entry-hour ∈ [07, 21) UTC, weekdays.

## Target (per horizon h)

- `r_h` = forward log-return over h bars, in bps.
- `σ_h` = trailing realized vol scaled to the horizon (from the per-bar rvol).
- **Train target = `r_h / σ_h`** (vol-normalized) for stability across pairs/regimes.
- **Eval conversion:** `pred_bps = pred_z × σ_h` to compare predictions to cost in
  real units.
- **No look-ahead:** all features shifted by ≥1 bar; target is strictly forward;
  purge a gap of `h` bars between train and test at the split boundary.

## Features (minimal price-only, ~5)

- `r_1` — last bar return (bps)
- `r_2_6` — short momentum (sum of returns over bars 2–6, shifted)
- `r_7_24` — longer momentum (sum over bars 7–24, shifted)
- `rvol_recent` — trailing realized vol (bps)
- `hour` — entry hour-of-day (raw or cyclical encoding)

No flow features, no spread-as-feature. Spread/commission enter **only as cost**.

## Model

- **Ridge** with `StandardScaler`; `alpha` tuned on the training set only.
- One model per (pair × horizon).
- **Validation:** 70/30 temporal split to start (matching the existing harness),
  with a purge gap of `h` bars at the boundary. Full walk-forward deferred to a
  later iteration if a cell survives.

## Evaluation — IC first, economics second

1. **Continuous IC:** Spearman(pred, actual) on the held-out set, per pair × horizon.
2. **Break-even bar:** `IC* = c_pair / σ_h` using the real per-pair costs above.
   Flag whether realized OOS IC clears `IC*`.
3. **Sign-stability:** IC sign consistent across train sub-folds and OOS.
4. **Breadth / multiplicity:** BH-FDR across the 6 pairs × 4 horizons.
5. **IC-by-hour:** Spearman bucketed by entry-hour within 07–21 to spot concentration
   (informs whether to later narrow toward the overlap window).

## Decision rules (one prediction, three monetizations)

All layered on the same `pred_bps`, reported side by side **net of `c_pair`**
(bar-close fills + flat cost; tick-exact verification deferred):

- **A — Always trade:** position = sign(pred), held h. Net = mean(sign(pred)·r_h) − c.
- **B — TP-sized:** position ∝ pred_bps (capped). Tests whether magnitude info adds value.
- **C — Cost-gated:** trade only when `|pred_bps| > c_pair`. Reports trade count + net.

## Outputs

Single results table: `pair × horizon → {N, OOS IC, IC*, clears?, sign-stable?,
BH-sig?, netA, netB, netC, n_trades_C}`, plus the IC-by-hour curve.

**Go/no-go gate:** a cell is a candidate only if it **clears IC\* AND is BH-significant
AND netC > 0**. Surviving cells graduate to tick-exact fill verification (separate work).

## Out of scope (YAGNI for v1)

Flow/microstructure features; cross-sectional pooling; regime clustering; tick-exact
fills; full walk-forward. Each is a follow-up only if a cell survives the screen.

# Strategy Master Manual (M5/M15) — Kalman + Rule‑Based MOM

**Version**: 7.0  
**Date**: February 2026  
**Status**: Rule‑based inference with mandatory guardrail

[!IMPORTANT]
This strategy **does not use CatBoost or any ML model**. All decisions are rule‑based on the Kalman Z‑score signal and the loss‑streak guardrail. Any legacy ML references in the repo are deprecated and not part of the live strategy.

---

## Executive Summary
This manual defines the production research strategy for the 5‑minute (M5) and 15‑minute (M15) systems. The strategy is **MOM‑only** and **rule‑based**:

1. **Kalman scout** computes a rolling Z‑score on the spread.
2. **MOM entry** triggers when `|Z| >= 1.5` (both signs allowed).
3. **Exit** when Z crosses 0 (mean‑reversion) or when `|Z| > 3.5` (momentum stop).
4. **Guardrail (mandatory)**: per‑symbol loss‑streak >= 3 triggers a **14‑day pause**.

This guardrail produces large drawdown reductions on both M5 and M15 while preserving positive expectancy.

---

## Strategy Overview (High‑Level)
The system trades synthetic spreads between asset pairs. A Kalman filter estimates a hedge ratio, then a rolling Z‑score of the spread residual triggers MOM entries. The active leg is chosen by the beta band (`beta < 0.98 => Y`, `beta > 1.02 => X`).

**Signal Summary**
- Entry (MOM): `|Z| >= 1.5`
- Exit:
  - **Loss / mean reversion**: Z crosses 0
  - **Win / momentum stop**: `|Z| > 3.5`
- Timeout: 500 bars
- Minimum gap between entries: 20 bars

**Required Risk Control**
- **Loss‑streak guardrail**: if a symbol has 3 consecutive losses, skip all its signals for 14 days.

---

## Detailed Strategy (How It Works)
This section is an exact, rule‑based specification.

### 1) Kalman Scout and Z‑Score
- Inputs: log prices `y = log(Y)`, `x = log(X)`
- Level Kalman filter estimates a rolling hedge ratio on mean‑centered prices.
- Spread error: `(y - mu_y) - beta * (x - mu_x)`
- Z‑score uses a 500‑bar rolling mean/std of spread error.

### 2) Active‑Leg Selection
- If `beta < 0.98`: **active leg = Y**
- If `beta > 1.02`: **active leg = X**
- Otherwise skip (neutral zone)

### 3) MOM Entry
- Entry when `|Z| >= 1.5`.
- Direction follows Z sign:
  - `Z > 0` → LONG spread on active leg
  - `Z < 0` → SHORT spread on active leg

### 4) Exit Logic (Z‑Based)
- **Loss / mean‑reversion**: Z crosses 0
- **Win / momentum stop**: `|Z| > 3.5`
- **Timeout**: 500 bars

### 5) Loss‑Streak Guardrail (Mandatory)
Per symbol:
- Track consecutive losses (trade‑level).
- If **loss‑streak >= 3**, pause the symbol for **14 calendar days**.
- After cooldown, trading resumes and streak resets.

Loss streak is computed from **PnL sign** (`pnl_bps <= 0` counts as a loss). **Win rate is not a KPI**; the sign of PnL is used only to enforce the guardrail.

This guardrail is **required at runtime**. Without it, drawdowns are materially larger.

---

## Strategy Plots (Guardrail Impact)
**Monthly Net PnL (Baseline vs Guardrail)**
- M5: `docs/figures/m5_guardrail_monthly_net.png`
- M15: `docs/figures/m15_guardrail_monthly_net.png`

**Drawdown Curves (Baseline vs Guardrail)**
- M5: `docs/figures/m5_guardrail_drawdown.png`
- M15: `docs/figures/m15_guardrail_drawdown.png`

---

## Results (Guardrail vs Baseline)
Results are **gross, cost‑free**, and computed over 2018–2025.
All reported performance stats use **PnL‑based win/loss** (`pnl_bps > 0`). The `outcome` label is a **signal outcome** (Z‑barrier logic) and is **not used** for performance reporting.

### M5 (MOM‑only)
- Baseline: 221,217 trades, mean 0.87 bps, max DD ‑68,685 bps, Sharpe 0.38
- Guardrail: 34,959 trades, mean 13.65 bps, max DD ‑6,030 bps, Sharpe 4.07

### M15 (MOM‑only)
- Baseline: 73,629 trades, mean 4.97 bps, max DD ‑41,531 bps, Sharpe 1.11
- Guardrail: 27,090 trades, mean 28.91 bps, max DD ‑5,718 bps, Sharpe 4.56

Full diagnostics:
- `data/analysis/m5_guardrail_overall.csv`
- `data/analysis/m5_guardrail_monthly.csv`
- `data/analysis/m5_guardrail_session.csv`
- `data/analysis/m5_guardrail_symbol.csv`
- `data/analysis/m15_guardrail_overall.csv`
- `data/analysis/m15_guardrail_monthly.csv`
- `data/analysis/m15_guardrail_session.csv`
- `data/analysis/m15_guardrail_symbol.csv`

---

## Reproducibility
**Dataset builders**
- M5: `scripts/build_meta_dataset_v3_m5.py`
- M15: `scripts/build_meta_dataset_v3.py`

**Guardrail diagnostics**
- M5: `scripts/report_m5_guardrail_diagnostics.py`
- M15: `scripts/report_mom_guardrail_diagnostics.py` (outputs `m15_guardrail_*.csv`)

**Guardrail WFO validation**
- `scripts/wfo_mom_loss_streak.py`
- Summary: `docs/analysis/mom_loss_limiter_wfo.md`

**Guardrail plots**
- `scripts/visualization/plot_guardrail_monthly_and_dd.py`

---

## Causality / Leakage Notes
- All features use only past bars at entry.
- Z‑score windows are rolling and causal (no forward data).
- Labels use future paths for evaluation only (as intended).

---

## Feature Dictionary (Kalman Scout)
These are the causal features used in dataset construction, even though inference is now rule‑based. Units in bps where noted.

Categorical features:
- `active_leg`: which leg is traded (X or Y).
- `side`: sign of Z at entry (LONG if Z>0, SHORT if Z<0).

Signal quality and lags:
- `z_entry`: Z‑score at entry.
- `z_velocity`: Z change vs 5 bars ago.
- `z_lag1`, `z_lag2`, `z_lag3`: Z at prior bars.
- `dz_lag1`, `dz_lag2`: short‑term slope proxies.
- `spread_std`: std of spread error over 500 bars (bps).

Beta and hedge context:
- `beta`: current Kalman beta.
- `beta_lag1`, `beta_lag2`: prior betas.
- `beta_stability`: beta std over 100 bars.
- `signal_beta_lookback`: mean beta over 500 bars.
- `hedge_beta_lookback`: mean return‑beta over 500 bars.
- `beta_mismatch`: clipped ratio `hedge_beta_lookback / signal_beta_lookback`.

Regime and correlation:
- `vol_ratio`: std(diff(Y)) / std(diff(X)) over 500 bars.
- `correlation_500`: corr(X,Y) over 500 bars.
- `trend_strength`: 100‑bar spread slope / spread std.

Time context:
- `hour`: entry hour (UTC).
- `day_of_week`: entry weekday.

Return and ATR context:
- `ret_X_16b`, `ret_Y_16b`: 16‑bar returns.
- `ret_X_1h`, `ret_Y_1h`: 1‑hour proxy returns.
- `atr_ratio`: 4‑bar range ratio (Y/X) over 100 bars.
- `entry_atr`: 50‑bar return std (bps).
- `vol_regime`: short/long volatility ratio (50/500).

---

## Deprecated / Not Used
- CatBoost models (classifier/regressor) are **not used**.
- Edge score thresholds are **not used**.
- REV strategy is **not traded**.

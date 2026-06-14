# FX USD-Factor Residual Mean-Reversion — Causal Selector Probe

**Date:** 2026-06-14  
**Branch:** worktree-fx-usd-factor-residual (PR #334+)  
**Question:** Can a supervised causal selector predict which 6–12 bps residual dislocations will revert next hour, lifting gross/net enough to clear measured spread cost?

---

## 1. Data & Method

- **Symbols:** 6 USD majors (EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD).
- **Bars:** 1000tick parquet → 5min aligned panel → hourly coarsen.
- **Factor:** Equal-weighted oriented USD-strength log return (no beta estimation, fully causal).
- **Residual:** Pair return minus factor.
- **Target band:** 6–12 bps |residual| (the "moderate-dislocation sweet spot" identified in PR #334).
- **Cost:** Measured hourly mean relative spread (`spread / mid`) per pair, not a fixed commission.
- **Label:** `y = 1` if fade wins (`−sign(residual_t) * residual_{t+1} > 0`).
- **Walk-forward:** 2-year train, 1-year OOS, 5-day purge gap. 7 windows spanning 2018–2026.

### Causal features (all known at entry hour `t`)

1. **Factor regime** — 6h & 12h rolling mean of intra-hour factor efficiency (`|net| / Σ|sub|`).
2. **Residual volatility** — 6h & 12h rolling std of pair residual.
3. **Cross-pair breadth** — fraction of pairs whose |residual| > 1σ (24h rolling).
4. **Cross-sectional dispersion** — std of residuals across the 6 pairs.
5. **Intra-hour path** — efficiency ratio + close-position from 5min sub-bars within the hour.
6. **Residual autocorrelation** — lag-1 correlation over 24h rolling window.
7. **Residual persistence** — signed sum over past 3h & 6h.
8. **Spread percentile** — current spread vs 24h median.
9. **Calendar** — UTC hour, day-of-week.
10. **Dislocation size** — |residual_t| in bps.

### Models

- **Baseline:** Always fade every pair-hour in the 6–12 bps band.
- **Logistic Regression** (`sklearn`, `C=1.0`, standardized features). Threshold selected on train to maximize net t-stat.
- **CatBoost** (`depth=4`, `iterations=200`, `l2_leaf_reg=5`). Only run if LR shows material OOS gross lift.

---

## 2. Results (aggregated across 7 walk-forward windows)

| Model      | Active% | n/window | Gross (bps) | Gross t | Net (bps) | Net t | Win% | Pos-month% |
|------------|---------|----------|-------------|---------|-----------|-------|------|------------|
| Baseline   | 100.0   | 1,193    | **+0.673**  | 1.2     | **−0.203**| −0.4  | 52.6 | 54         |
| Logistic   | 25.8    | 278      | **+0.761**  | 0.7     | **−0.101**| −0.1  | 52.3 | 55         |
| CatBoost   | 28.6    | 260      | **+0.649**  | 0.4     | **−0.185**| −0.4  | 55.1 | 49         |

### Interpretation

- **The 6–12 bps band is sub-cost on a 6-pair cross-sectional basis.** Baseline gross +0.67 bps, net −0.20 bps after measured spreads. The earlier EURUSD-only finding of net +0.18/+0.24 bps (at a 0.65 fixed commission) does **not** generalize to a diversified 6-pair book because wider-spread pairs (GBPUSD, USDCHF, USDCAD, AUDUSD) drag the average cost above the average capture.
- **Logistic regression produces marginal gross lift** (+0.09 bps) by filtering out some losing trades, but the lift is far below the spread cost. Net improves from −0.20 to −0.10 bps — still negative.
- **CatBoost does not help.** Despite astronomical train-set net t-stats (16–19), OOS gross is actually *lower* than baseline (+0.649 vs +0.673). The model overfits the training noise; more capacity makes it worse, not better.
- **Win rates are barely above coin-flip.** Even the "selected" subset is ~52–55% — the signal is too faint for a binary classifier to separate reliably.

### LR coefficients (last window)

| Feature            | Coef   | Directional interpretation                     |
|--------------------|--------|--------------------------------------------------|
| factor_eff_6       | −0.15  | Lower efficiency (choppy) → slightly more revert  |
| pers_3             | +0.21  | Recent persistence → model thinks revert (noise?) |
| factor_eff_12      | +0.12  | Contradicts the 6h version                       |
| res_vol_12         | +0.08  | Higher vol → slightly more revert                |
| dispersion         | +0.07  | More dispersion → slightly more revert           |
| intra_efficiency   | +0.06  | Higher intra-hour efficiency → more revert       |
| pers_6             | −0.11  | Longer persistence → less revert                 |
| breadth            | −0.07  | More pairs dislocating → less revert             |
| spr_pct            | −0.06  | Wider spread → less revert                       |
| disloc_bps         | −0.01  | Size within band → negligible                    |

Coefficients are small, inconsistent across windows, and do not point to a robust causal structure. The model is essentially fitting noise.

---

## 3. Honest verdict

**Model capacity does not convert to P&L here because the signal is below the cost floor.**

The 6–12 bps band was the best-sampled, highest-win-rate zone in the univariate analysis, but that analysis was EURUSD-centric and used a fixed-commission assumption. On the actual 6-pair cross-section with measured spreads:

- Average gross capture ≈ 0.67 bps.
- Average measured spread cost ≈ 0.87 bps.
- Margin = −0.20 bps.

Even a perfect selector that kept only winning trades would cap out at ~1.28 bps gross (0.67 / 0.526), yielding ~+0.40 bps net on half the sample. No realistic model approaches perfection. Logistic achieves +0.76 bps gross on 26% of trades — a small, unstable lift that is swallowed by cost.

**Boosting is decisively ruled out.** CatBoost overfits massively (train t-stats 16–19, OOS net still negative). The hourly residual is fundamentally unpredictable at this signal-to-noise ratio.

---

## 4. What *would* help (scoped to this signal)

| Lever                     | Expected impact | Honest assessment                        |
|---------------------------|-----------------|------------------------------------------|
| Restrict to tight pairs   | High            | EURUSD-only or tight-3 book may clear cost; test next |
| Lower cost (ECN/commission) | High            | Commission-based broker (~0.3 bps/side) vs spread-betting (~1.2–1.8 bps); decisive |
| Lower frequency (daily/weekly) | High       | Cost negligible vs move size; only other surviving FX edge lives here |
| More sophisticated model  | Low/negative    | Signal is below noise floor; capacity → overfit |
| Exact 5-min sub-bar timing| Marginal        | Already engineered; no transformative leverage left |

---

## 5. Files / artifacts

- `scripts/fx_coint/residual_selector.py` — causal selector prototype (walk-forward LR + CatBoost).
- `tests/fx_coint/test_residual_selector.py` — look-ahead guard + regime-lift smoke tests.
- `scripts/fx_coint/usd_factor_residual_probe.py` — original hourly probe (untracked, root checkout).
- `scripts/fx_coint/usd_factor_move_distribution.py` — cost-sensitivity by move-size band (untracked, root checkout).

---

## 6. Next (if continuing this thread)

1. **Tick-exact fills on EURUSD 6–12 bps band** — the margin-deciding test for the only pair that might clear cost.
2. **Lower-frequency port** — daily/weekly factor-residual reversion, where cost is not the binding constraint.
3. **Close this avenue** — record as another model-proof NO-GO and redirect modeling capacity to the weekly mean-reversion signal (the only surviving FX edge).

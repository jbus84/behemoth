# Signed-Return Regression Model + Purged CV — Design

**Date:** 2026-06-24
**Status:** Approved (design); pending spec review
**Location:** `scripts/fx_coint/`, reports in `reports/model_search/`

## Problem

The assessment phase proved the features carry real but weak structure, that
IC ≠ tradeable edge, and that magnitude + cost decide tradeability. Now we build
**models** that exploit the features by predicting expected signed return (µ),
then trade `sign(µ)` and select/size by `|µ|`. The model must prove edge on the
walk-forward net-bps gate — Ridge is the floor, complexity must earn its place.

## Non-goals

- Not classification — barrier sign labels throw away the magnitude the edge
  lives in. Regression on signed return.
- No new feature construction — reuse the ~25 tick-native features from `build_all`.
- No deep nets / TSER — this program's evidence has them losing to Ridge.

## Target & data

- **Target:** signed first-touch return in **bps**, N-bar triple-barrier,
  vol-scaled symmetric barriers `1.0 * vol * sqrt(N)`. **N=50 primary** (the
  only taker-survivable horizon from the assessment); **N=30** as a robustness
  check.
- **Features:** the full ~25 tick-native set from `feature_ic_definitive.build_all`
  (engineered-lag + microstructure + De Prado price-only). The model's job is the
  nonlinear *combination* — the edge search found no single durable marginal feature.
- **Pool:** 5 ex-JPY majors `["AUDUSD","EURUSD","GBPUSD","USDCAD","USDCHF"]`,
  40000 events/symbol (seed 0), pooled.
- **Prediction → action:** `sign(µ)` = side; `|µ|` = conviction → top-decile
  selection + sizing.

## Model ladder

Each rung must beat the rung below it on **walk-forward non-overlap net-bps** to
justify its added complexity:

1. **Ridge** — the proven floor (`alpha` tuned).
2. **Ridge + motivated interactions** — explicit product terms (`ffd_zvol20 ×
   dev_age`, `ffd_zvol20 × adf_sup`) appended to the linear design, transparent
   interaction capture.
3. **HistGBM** (`HistGradientBoostingRegressor`) — the nonlinear arm, with:
   monotonic constraints where a sign is believed (e.g. ffd→reversion), heavy
   regularization (large `min_samples_leaf`, `l2_regularization`, low
   `learning_rate`, `early_stopping`).
4. **Bagged HistGBM** — variance reduction via **sequential bootstrap** (AFML ch4,
   `sample_weights.seq_bootstrap`) for low-overlap bags; bag predictions averaged.

## Fitting & tuning

- **Sample weights:** return-attribution (`sample_weights.return_attribution_weights`
  — uniqueness 1/concurrency × |return|), passed to each estimator's `fit`. Time-
  decay off initially (a later regime-drift knob).
- **Cross-validation:** **PurgedKFold** (de Prado AFML Snippet 7.3) implemented as
  a sklearn-compatible splitter using `t1` (label-end indices from
  `triple_barrier_core`) — purge train observations whose label interval overlaps
  the test interval, plus a post-test embargo (`pctEmbargo`). Used for
  hyperparameter selection only.
- **CV scorer:** a regression/edge scorer (Spearman IC of predicted µ vs realized
  return, and/or in-fold net-bps of the µ-driven strategy) — NOT log_loss/accuracy
  (the AFML `cvScore` snippet is classification-only; we swap the scorer).

## Final gate (the arbiter)

Each fitted model produces µ on a held-out **walk-forward, non-overlapping** OOS
path (reuse `pnl_walkforward` machinery, thresholds/fit per expanding fold). The
strategy: `sign(µ)` side, top-decile `|µ|` selection, realistic round-trip cost
(1.0 bps primary). Report net-bps/trade, folds-positive, symbols-positive — and
compare to (a) the fixed base (fade `ffd_zvol20` × top-decile `|ffd_zvol20|`) and
(b) Ridge. **A model wins only if it beats both the base and Ridge, robustly
across folds and symbols.**

## Modules

- `purged_kfold.py` — `PurgedKFold` splitter (purge + embargo via `t1`) + the
  edge/IC CV scorer. The reusable CV primitive; pure + unit-tested.
- `model_search.py` — the ladder: build design matrix (features + interaction
  terms), fit each model with return-attribution weights, tune via PurgedKFold,
  predict µ. Thin `main()` orchestrates.
- extend `pnl_walkforward.py` — a model-µ-driven strategy evaluator reusing the
  non-overlap + expanding-fold machinery (analogous to `marginal_lift`, but the
  selector is `|µ|` and the side is `sign(µ)`).
- `reports/model_search/` — PurgedKFold CV scores, walk-forward net-bps per model
  vs base/Ridge, plots, REPORT.md.
- Tests in `tests/fx_coint/` for `PurgedKFold` (purge/embargo correctness on
  synthetic overlapping labels — no train label may overlap the test interval;
  embargo drops the right post-test rows) and the edge scorer.

## Guardrails

- **Two CV tools, two jobs:** PurgedKFold for tuning (data-efficient, honest under
  overlap); walk-forward non-overlap for the final P&L (live-like, mirage-proof).
- **Ridge is the baseline** every rung must beat on net-bps — complexity is not
  assumed to win (this program's repeated finding).
- **Bagging done AFML-correctly:** sequential bootstrap, not naive bootstrap
  (overlapping labels make naive bags non-independent and overstate variance
  reduction).
- **Multiplicity:** the ladder is a small fixed set; judged on OOS walk-forward
  net-bps, not CV score; report how many models/horizons were evaluated.
- **No look-ahead:** PurgedKFold purge+embargo from `t1`; walk-forward thresholds
  train-only; sample weights computed within train folds.

## Decisions locked

- Target = signed first-touch return bps (A), N=50 primary / N=30 robustness.
- Single signed-return regressor (µ serves both side and conviction) — not
  two-track models.
- Sample weight = return-attribution (uniqueness × |return|).
- Ladder: Ridge → Ridge+interactions → HistGBM → bagged-HistGBM (seq bootstrap).
- PurgedKFold for tuning; walk-forward non-overlap net-bps as the final arbiter.

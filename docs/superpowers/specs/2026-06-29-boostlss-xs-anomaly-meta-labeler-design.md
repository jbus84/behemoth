# BoostLSS Cross-Sectional Anomaly Detection + Meta-Labeler

**Date:** 2026-06-29
**Status:** Approved — pending implementation plan

---

## Overview

Model the full conditional return distribution across a 21-pair FX universe at 1000-tick
resolution using BoostLSS (JSU family). Identify `(symbol, bar)` observations where the
predicted distribution is anomalous across four channels (location, scale, tail-fatness,
skewness), then pass flagged points to a downstream HistGBM meta-labeler that assesses
whether the predicted anomaly yields a profitable 5-bar trade.

This is a gross-signal exploration — costs are excluded from this stage.

---

## 1. Data & Universe

- **Bars:** 1000-tick bars from `data/tick_bars/` (existing parquet per pair)
- **Universe:** All 21 pairs with parquet coverage, ~2018–2025
- **Orientation:** Each pair's return oriented to USD-strength (existing `PAIRS` sign convention)
- **Vol-standardization:** Applied before pooling; USDJPY gets `is_jpy=1` flag rather than exclusion
  (homogeneity F-test p=0.93 ex-JPY, p=0.0017 with — isolate via flag, do not drop)
- **Row:** `(symbol, tick_bar_index)` — ~21 pairs × ~150 bars/day × 1750 days ≈ 5.5M rows
- **Target:** Gross log-return over next N=5 tick-bars (no cost adjustment at this stage)

---

## 2. Feature Matrix

Each row carries two feature groups, computed causally (no look-ahead).

### Within-symbol features

| Feature | Definition |
|---|---|
| Rolling log-returns | L = 5, 10, 20, 50, 100 bars — raw |
| Realized vol (robust) | Rolling MAD-based: 1.4826 × median\|r − median(r)\| at L = 20, 50 |
| Momentum signal | Rolling quantile rank of return within own history — distribution-free |
| Bar activity | n_ticks per bar (urgency proxy) |
| Time features | Hour-of-day, day-of-week, session flag (Asia / London / NY) |
| Vol-of-vol | Rolling MAD of rolling MAD — regime instability |
| Rolling kurtosis | Excess kurtosis of own returns over last 50 / 100 bars |
| Tail event count | Bars in last 100 where \|return\| > 3 × rolling MAD |

### Cross-sectional features (backward as-of join, look-ahead-free)

| Feature | Definition |
|---|---|
| XS rank | Ordinal rank of symbol's L=20 return within 21-pair universe at bar T |
| XS robust z | (symbol return − XS median) / (1.4826 × XS MAD) |
| USD-factor residual | Causal rolling-OLS residual vs. USD basket mean (`cross_symbol.py` pattern) |
| XS IQR | Q75 − Q25 of universe returns at bar T (scale of cross-sectional spread) |
| XS IQR trend | Bar-over-bar change in XS IQR (is spread widening or compressing) |
| XS dispersion z-of-z | How extreme today's XS IQR is relative to its own rolling history (IQR-on-IQR) |
| LOO robust z | Symbol vs. peer median/MAD excluding self |
| XS kurtosis | Kurtosis of universe return distribution at bar T |
| XS bimodality | Hartigan's dip statistic on universe returns at bar T |
| Pairwise corr mean | Rolling mean pairwise correlation across universe — systemic factor strength |
| Momentum × vol-of-vol | Quantile rank × vol-of-vol interaction |
| `is_jpy` | Binary flag for USDJPY |
| Symbol | Categorical (LightGBM native encoding) |

**Note on z-scores:** All cross-sectional standardization uses median/MAD (robust), not
mean/std, consistent with the JSU distributional assumption. Standard z-scores are avoided
throughout — they would embed a Gaussian assumption that contradicts the model's purpose.

---

## 3. BoostLSS Model

### Distribution family

**JSU (Johnson Su)** — 4 parameters: (μ, σ, ν, γ).

| Parameter | Meaning | Why JSU over Student-t |
|---|---|---|
| μ | Location (conditional mean) | Same |
| σ | Scale (conditional spread) | Same |
| ν | Tail-fatness (d.f. analogue) | Same as Student-t |
| γ | Skewness | **New** — Student-t is symmetric; JSU captures directional asymmetry |

Student-t was rejected because FX returns in trending/event regimes have asymmetric tails.
Predicted γ ≠ 0 is directly actionable (positive γ = position for right-tail outcome).
SHASHo is a noted alternative if skewness and kurtosis need independent control.

### Model structure

- One BoostLSS model, pooled rows, symbol as categorical
- Four separate tree ensembles, one per parameter — each sees the full feature set
- Expected feature importance split: scale-predictive features (vol-of-vol, XS IQR, corr)
  dominate σ trees; shape-predictive features (rolling kurtosis, tail count, XS kurtosis)
  dominate ν / γ trees — verify post-fit as sanity check

### Walk-forward

- 5 causal folds, ~1.5yr expanding train / 6mo test
- Hyperparameters (learning rate, max depth, num trees) tuned on fold 1 only, held fixed
- No look-ahead in any XS feature (backward as-of join throughout)
- BoostLSS predictions generated OOS-only before being passed to meta-labeler

---

## 4. Flagging — Four Channels

Each `(symbol, bar)` observation in the OOS window is scored on four independent channels:

| Channel | Trigger | Signal |
|---|---|---|
| **μ** (directional) | \|predicted μ\| > 1.5 × unconditional MAD of returns | Direction = sign(predicted μ) |
| **σ** (calm-regime) | predicted σ < 20th percentile of in-fold training σ | Size up in calm windows |
| **ν** (fat-tail) | predicted ν < 5 | Expect extreme move; widen stops |
| **γ** (skewness) | \|predicted γ\| > 0.5 | Direction = sign(predicted γ) |

Each channel outputs:
- Binary flag (0/1)
- Continuous magnitude (|predicted parameter value|)

Both are passed to the meta-labeler. Thresholds are starting values — calibrate per fold.

---

## 5. Meta-Labeler

### Purpose

Assess whether a flagged `(symbol, bar)` observation actually yields a profitable 5-bar
gross return in the predicted direction. The meta-labeler sits cleanly downstream — it
receives only BoostLSS OOS predictions, never raw features.

### Inputs

- Four binary flags (μ, σ, ν, γ)
- Four continuous magnitudes
- Co-firing interactions: which channel pairs fired together
- Direction consensus: do μ and γ channels agree on sign?

### Label

Binary: did the next-5-bar gross return exceed the unconditional median of |5-bar returns|
for that symbol, in the predicted direction? (Threshold is distribution-appropriate and
symbol-specific, not a fixed bps value.)

### Model

HistGBM classifier (consistent with `short_term_metalabel_probe.py`). Purged WFO aligned
to the same folds as BoostLSS — meta-labeler training data never includes BoostLSS
predictions from its own training window.

### Output

P(profitable | flags fired). Act if P > 0.55 (tunable). Abstain if μ and γ channels
conflict on direction.

---

## 6. Action Logic

| Decision | Rule |
|---|---|
| Direction | Consensus of μ and γ. Conflict → abstain. |
| Size | Inverse of predicted σ, normalized to fixed risk budget per bar |
| Hold | Fixed N=5 tick-bars (no dynamic exit — held until bar 5) |
| Universe collision | Size each symbol independently; cap total gross exposure at 3× single-position size |

### Output artifact

Per-fold trade log: `(symbol, entry_bar, direction, size, 5bar_gross_return, channel_flags, meta_prob)`
Enables per-channel PnL attribution and post-hoc channel importance analysis.

---

## 7. Progression Plan

- **Phase A (this spec):** Approach A — JSU BoostLSS, four-channel flagging, HistGBM meta-labeler
- **Phase B:** Upgrade to Skewed-t (SHASHo) or composite anomaly score if JSU γ channel is
  weak or uninterpretable
- **Phase C:** Separate per-moment BoostLSS models with ensemble meta-labeler if Phase A
  reveals that different feature subsets dominate different parameters

---

## 8. Key Implementation Dependencies

- `scripts/cross_symbol.py` — XS alignment, backward as-of join pattern
- `scripts/era_scalp/xs_atomic_concepts.py` — LOO robust z, dispersion rank operators
- `scripts/fx_coint/xs_reversion.py` — daily_returns() and residualise() patterns
- `scripts/short_term_metalabel_probe.py` — purged WFO meta-labeler pattern
- `data/tick_bars/` — 21-pair parquet source
- `boostlss` Python package (https://github.com/dnf0/boostlss) — to be added to dependencies

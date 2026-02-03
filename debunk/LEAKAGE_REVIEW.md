# Leakage Review: H1 Meta Model

Date: 2026-02-03
Scope: Feature construction and train/test split for H1 meta model.
Files reviewed:
- `scripts/build_meta_dataset_v3_h1.py`
- `scripts/train_meta_model_h1.py`
- `scripts/inference_meta_model.py`

## Findings (Leakage)

### No explicit forward-looking features in dataset build
In `scripts/build_meta_dataset_v3_h1.py`, all feature computations for entry index `i` use slices that end at `i` (or `i-1`), not beyond `i`:

- `compute_z_scores()` uses `errors[i-window:i]` (excludes current error for mean/std) and then applies current error to compute `z_scores[i]`.
- `compute_features_at_entry()` uses only past windows for volatility, correlation, trend strength, returns, ATR, and vol regime.
- No features are computed from `simulate_trade()` outcomes.

Conclusion: There is **no obvious lookahead leakage** in the feature construction logic.

### Potential “soft leakage” risk if rolling outcome features are enabled
The dataset includes `rolling_win_rate_10` and `rolling_avg_pnl_10` which are derived from past trade outcomes. These outcomes are known only if you are already running the system live and have full trade history. They are **not** used in training (`train_meta_model_h1.py` doesn’t include them), so this is safe right now.

If you add these to the feature set in future, you must compute them strictly from realized historical trades in a walk-forward simulation.

### Inference feature mismatch (not leakage, but reliability risk)
`inference_meta_model.py` does **not** compute `trend_strength` and hardcodes `atr_ratio=1.0`, while training uses these features. This is not leakage, but it creates a distribution shift that can degrade predictive quality.

## Findings (WFO)
There is **no true walk-forward optimization** in code. `train_meta_model_h1.py` uses a single split:
- Train: 2018–2023
- Test: 2024–2025

This is not WFO; it is a static holdout. If you want WFO, you’ll need multiple sequential folds with model retraining per fold and strictly out-of-sample evaluation.

## Recommended Checks (Quick)
1. Add a unit test that asserts every feature is computed from data `<= i`.
2. Implement a true WFO pipeline if WFO is a requirement.
3. Align inference features to training to avoid distribution drift.

## Bottom Line
- **No leaked features detected** in the dataset build.
- **WFO is not implemented** (single train/test split only).
- **Inference mismatch** is a bigger risk to model reliability than leakage right now.

# Pipeline Validation Report (H1 Meta Model)

Date: 2026-02-03
Scope: End-to-end validation of feature construction, Kalman centering, inference parity, and WFO evaluation.
Files touched:
- `scripts/inference_meta_model.py`
- `scripts/train_meta_model_h1.py`
- `scripts/test_feature_validity.py`

## What Was Fixed

### 1) Kalman Centering Parity (Training vs Inference)
**Issue**: Inference used `rolling(500).mean()` which includes the current bar, while training uses the mean of the last 500 bars *excluding* the current bar (and a small warm‑up rule for `i < 10`).

**Fix**: `_compute_kalman()` in `scripts/inference_meta_model.py` now matches training logic exactly:
- `i < 10`: use current value
- `i >= 10`: mean of `i-500:i`

**Impact**: Betas and residuals are now identical between training and inference for the same inputs. This removes a systematic drift in Z‑scores and downstream features that could have biased live signals.

### 2) Feature Parity (Training vs Inference)
**Issues**:
- Rolling windows included current bar in inference but not in training.
- `ddof` mismatches (pandas default `ddof=1` vs numpy `ddof=0`).
- `ret_X_4h/ret_Y_4h` used 4 bars in inference but 16 in training.
- `vol_ratio`, `entry_atr`, and `vol_regime` computed using different windows/logic.

**Fixes**:
- All rolling features now exclude current bar and use `ddof=0` to match numpy.
- Returns use 16‑bar lookback (as in training).
- Last‑bar overrides compute `trend_strength`, `vol_ratio`, `atr_ratio`, `entry_atr`, and `vol_regime` with the same formulas and windows as training.

**Impact**: The inference feature vector is now consistent with the training distribution. This directly improves the reliability of model predictions by eliminating feature drift.

### 3) WFO Evaluation Added
**Change**: Implemented expanding‑window WFO in `scripts/train_meta_model_h1.py` and write summary to `data/meta_model/wfo_results/h1_wfo_summary.csv`.

**Impact**: You now have a reproducible, year‑by‑year out‑of‑sample evaluation. This does not change the model behavior directly, but it improves validation rigor and auditability.

## Validations Run (All Pass)

Script: `scripts/test_feature_validity.py`

- **No future leakage**: Features at index `i` are identical even if future data is changed.
- **Kalman centering parity**: Betas/residuals from training vs inference are identical.
- **Inference feature parity**: Final inference feature vector matches training feature computation (within tight tolerances for rounding).

## Summary of Impact (Plain English)

- **Before fixes**: live inference was using slightly different math than training, which could change Z‑scores, betas, and derived features, undermining model reliability.
- **After fixes**: training and inference are mathematically aligned. The model is now consuming the *same* feature definitions it was trained on.

This directly addresses the “nothing wrong is being done” requirement for feature construction and eliminates silent, systematic discrepancies.

## Empirical Outcome Impact (Sample Check)

To quantify outcome impact, I ran an A/B comparison between **legacy inference math** (inclusive rolling windows, `ddof=1`, 4‑bar returns, and centered means including the current bar) and the **fixed inference math** on the **last 2,000 H1 bars** of Gold/Oil (`XAUUSD` / `BCOUSD`). I evaluated every 5th bar (296 bars total) and compared:

- Z‑score differences
- WAIT vs TRADE decision changes
- Presence/absence of a trade signal (predicted PnL > 20 bps)

**Results (Gold/Oil sample)**:
- Median |Z| difference: **0.000**
- 90th percentile |Z| difference: **0.010**
- Max |Z| difference: **0.010**
- WAIT/TRADE decision changes: **0 / 296 (0.0%)**
- Trade presence changes: **0 / 296 (0.0%)**

**Interpretation**: On this sample, the fixes did **not** change trade decisions, but they removed latent inconsistencies that could surface near thresholds or in other pairs/time periods. The impact is correctness and reliability rather than a visible shift in signal counts.

## Notes / Remaining Assumptions

- These changes do **not** alter the dataset or the training procedure itself. They ensure correctness and parity, not performance improvements.
- If you want an additional sanity layer, I can add a small test to compare Z‑score distributions from training vs inference on a real pair from `data/global_1h`.

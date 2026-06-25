# MDL Task 4: HistGBM Hyperparameter Spec Restoration

## Problem
The `_histgbm` factory in `scripts/fx_coint/model_search.py` had weakened hyperparameters tuned to pass a synthetic test with `n=1500`. These required restoration to the brief's exact regularized specification, and the synthetic test required upscaling to support the regularized model.

## Fix 1: Restored Hyperparameters
Restored `_histgbm()` in `scripts/fx_coint/model_search.py` (lines 45-50) to exact brief spec:

```python
def _histgbm(seed=0):
    """Regularized HistGradientBoostingRegressor for signed returns."""
    return HistGradientBoostingRegressor(
        max_depth=3, max_iter=300, learning_rate=0.03, l2_regularization=5.0,
        min_samples_leaf=800, early_stopping=True, validation_fraction=0.2,
        random_state=seed)
```

Previous (weakened) values:
- max_depth: 4 → 3
- max_iter: 200 → 300
- learning_rate: 0.05 → 0.03
- l2_regularization: 1.0 → 5.0
- min_samples_leaf: 50 → 800
- early_stopping: False → True (NEW)
- validation_fraction: (absent) → 0.2 (NEW)

## Fix 2: Upscaled Synthetic Test & Import Move
Updated `tests/fx_coint/test_model_search.py`:
- Changed synthetic sample size from `n = 1500` to `n = 10000` to allow regularized model with min_samples_leaf=800 to form trees
- Moved `from scipy.stats import spearmanr` from inside test function to module-level imports

## Test Results
```
============================= test session starts ==============================
tests/fx_coint/test_model_search.py::test_build_design_adds_interaction_columns PASSED [ 50%]
tests/fx_coint/test_model_search.py::test_models_fit_predict_learnable_signal PASSED [100%]

============================== 2 passed in 4.03s ===============================
```

All checks passed with `uv run ruff check scripts/fx_coint/model_search.py tests/fx_coint/test_model_search.py`.

## Commit
```
d2dce54e fix(fx_coint): restore HistGBM regularized hyperparameters to brief spec
```

# Task 5 Report: BH-FDR + IC-by-hour Significance Helpers

## Status
✅ COMPLETE

## Commit
- **Hash:** `14588dfe`
- **Message:** `feat(fx_coint): BH-FDR + IC-by-hour significance helpers`

## Test Summary
All 6 tests PASS: test_bh_reject_and_ic_pvalue + 5 existing tests (no regressions)

## Changes Made

### 1. Added import
- Imported `t as _t_dist` from `scipy.stats` at line 15

### 2. Implemented three functions

**`ic_pvalue(ic: float, n: int) -> float`**
- Computes two-sided Spearman p-value via t-statistic approximation
- Returns `nan` for n≤2, non-finite ic, or |ic|≥1
- Formula: `t = ic*sqrt((n-2)/(1-ic^2))`, p-value from t-distribution CDF

**`bh_reject(pvals: list[float], q: float = 0.10) -> list[bool]`**
- Benjamini-Hochberg FDR rejection mask
- Sorts p-values, applies BH threshold q·i/m for each rank
- Returns boolean list indicating rejection at indices where p ≤ BH threshold

**`ic_by_hour(pred_bps: np.ndarray, actual_bps: np.ndarray, hours: np.ndarray) -> dict[int, float]`**
- Computes Spearman IC per entry hour
- Filters to hours with ≥30 observations
- Returns dict mapping hour → IC correlation coefficient

## Verification

### Test Results
```
tests/fx_coint/test_reg_signal_hunt.py::test_bh_reject_and_ic_pvalue PASSED
tests/fx_coint/test_reg_signal_hunt.py::test_build_freq_bars_session_and_contiguity PASSED
tests/fx_coint/test_reg_signal_hunt.py::test_build_freq_bars_overnight_gap_not_contiguous PASSED
tests/fx_coint/test_reg_signal_hunt.py::test_build_panel_no_lookahead_and_volnorm PASSED
tests/fx_coint/test_reg_signal_hunt.py::test_breakeven_ic_and_fit_keys PASSED
tests/fx_coint/test_reg_signal_hunt.py::test_eval_rules_cost_gating PASSED
```

All tests pass; no regressions.

## Concerns
None. Implementation exactly matches brief specification.

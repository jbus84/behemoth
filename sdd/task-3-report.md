# Task 3: `cell_stats` — Report

## Status
✅ COMPLETE

## Commit
`b0bb4f72` — feat(fx_coint): cell_stats significance + per-fold robustness

## Test Summary
All 3 tests in `tests/fx_coint/test_tail_wfo.py` pass:
- `test_walk_forward_folds_expanding_and_oos` PASSED
- `test_gate_trades_uses_train_threshold_long_and_short` PASSED
- `test_cell_stats_known_arrays` PASSED (new)

## Implementation
Added `cell_stats(net: np.ndarray, fold_id: np.ndarray) -> dict` to `scripts/fx_coint/tail_wfo.py`:
- Returns dict with keys: `n`, `mean_net_bps`, `t_stat`, `p_value`, `pos_fold_pct`, `hit_rate`, `total_net_bps`
- Computes two-sided one-sample t-test vs 0 using `scipy.stats.ttest_1samp` (already imported)
- Sets `t_stat` and `p_value` to `nan` if `n < 3`
- Computes `pos_fold_pct` as fraction of distinct folds with positive mean net (or `nan` if no folds)
- Handles empty arrays gracefully

## Concerns
None. Implementation followed brief exactly:
- Test written and failed as expected (function not defined)
- Minimal implementation added and test passed
- All existing tests continue to pass
- Commit includes proper trailer
- No modifications to existing functions

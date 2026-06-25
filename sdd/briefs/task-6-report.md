# Task 6 Report: Stage A Block-Permutation Null + Ceiling Bracket

## Status
**DONE**

Commit: `73f9ff0d`

## Summary

Implemented three functions in `scripts/fx_coint/target_ceiling.py`:

1. **`block_permutation_null(stat_fn, y, block_len, n_draws, rng)`**  
   Computes a null distribution by shuffling contiguous blocks of the target array `y`, preserving short-range autocorrelation. Returns an array of `n_draws` statistics.

2. **`_emp_p_z(obs, null)`**  
   Helper that computes empirical p-value (fraction of null ≥ obs) and z-score relative to null distribution. Handles NaN values gracefully.

3. **`ceiling_bracket(X, y, t1, kind, block_len=50, n_draws=50, embargo=10, rng=None)`**  
   Main interface that estimates predictability ceiling as a bracket:
   - **Lower bound**: gradient-boosted model skill (Spearman IC or balanced accuracy) on own-history lags
   - **Upper estimate**: kNN mutual information
   - Both compared to block-permutation nulls; returns empirical p and z for each

## Tests (3 appended to `tests/fx_coint/test_target_ceiling.py`)

- `test_block_permutation_null_preserves_length_and_values`: Verifies block permutation returns correct shape and preserves mean of identical values.
- `test_ceiling_bracket_signal_beats_null`: Strong learnable signal (lag-1/lag-2 dependence) beats null with p < 0.1, z > 2.0.
- `test_ceiling_bracket_noise_indistinguishable_from_null`: Pure noise fails to reject null (p > 0.1).

All 10 tests in the suite pass in 21.79 seconds; quality checks (type, ruff, vulture, smell) pass.

## Implementation Notes

- **Block permutation**: Shuffles whole blocks to preserve temporal structure (guards against overstating significance).
- **Empirical p**: Uses continuity correction `(count + 1) / (n + 1)` to avoid p=0 on finite samples.
- **NaN handling**: Filters finite values from null before computing stats; returns (NaN, NaN) if null empty or obs non-finite.
- **Default RNG**: Defaults to `np.random.default_rng(0)` if not provided, consistent with other functions.
- **Integration**: Calls existing `model_lower_bound` and `knn_mi` (Task 5) under permuted targets.

## Verification

```bash
make quality  # All checks pass
uv run pytest tests/fx_coint/test_target_ceiling.py -v  # All 10 pass (Tasks 4+5+6)
```

Tests run in expected ~20–30 seconds due to n_draws=30 permutations × expensive CV/MI calls per permutation (as specified in brief).

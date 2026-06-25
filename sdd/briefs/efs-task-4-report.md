# EFS Task 4 — pnl_walkforward.py Review Fix Report

## Findings and Fixes

### C1 — Look-ahead leakage in magnitude role (Critical)
**Problem:** `_rank(np.abs(d["sel"]))` and `_rank(np.abs(d["feat"]))` ranked over the ENTIRE series (train + test). The 0.90 quantile of `comb` also used full-array data, so test-trade thresholds saw future values.

**Fix:** Added pure helper `train_relative_topdecile(sel_abs, feat_abs, tr_mask, q=0.90) -> np.ndarray`. It uses `np.searchsorted` into sorted train arrays to give every row a train-relative percentile, computes combined score, and derives the threshold from the 0.90 quantile of **train-only** combined scores. The `cand_select` magnitude branch now calls:
```python
return te & train_relative_topdecile(np.abs(d["sel"]), np.abs(d["feat"]), tr) & np.isfinite(d["pnl"])
```

### I1 — Direction orientation parameter (Important)
**Problem:** No way to align an anti-correlated feature with the fade direction.

**Fix:** Added `orient: float = 1.0` parameter to `marginal_lift`. In the direction branch: `feat = orient * d["feat"]` before `np.sign(feat)`. Docstring updated with explanation.

### I2 — n_trades mislabeled (Important)
**Problem:** `n_trades` returned `len(cand_net)` (fold count, 4), not the real trade count.

**Fix:** `fold_net` now accumulates `total_trades` (count of non-overlapping trades across all folds/symbols) and returns `(nets_array, total_trades)`. Both `base_net`/`cand_net` call sites updated. `n_trades` set to `cand_trades` (real trade count).

### M1 — Module-level import (Minor)
**Fix:** Moved `from scipy.stats import rankdata` to top-level imports; removed the inline import inside `_rank`.

### M3 — Conditioner branch silent fallback (Minor)
**Problem:** If no tercile had >20 train trades, `best` stayed `0` and silently used tercile 0.

**Fix:** Initialized `best = None`. After loop, if `best is None`, return `np.zeros(len(te), dtype=bool)` (all-False mask) instead of silently selecting tercile 0.

## New Test

**`test_train_relative_topdecile_no_leakage`** in `tests/fx_coint/test_pnl_walkforward.py`

Builds 100 train rows from U[0,1] and 10 test rows. Runs twice: once with normal test values (U[0,1]), once with extreme test values (U[900,1000]). Asserts that the fraction of train rows selected is identical in both cases — proving the threshold is calibrated train-only. A naive full-rank implementation would produce a lower train-selected fraction when extreme test values inflate the ranking scale.

## Test Run

```
uv run pytest tests/fx_coint/test_pnl_walkforward.py -v

tests/fx_coint/test_pnl_walkforward.py::test_greedy_nonoverlap_excludes_overlapping_holds PASSED
tests/fx_coint/test_pnl_walkforward.py::test_greedy_nonoverlap_all_disjoint_kept PASSED
tests/fx_coint/test_pnl_walkforward.py::test_train_relative_topdecile_no_leakage PASSED

3 passed in 1.40s
```

```
uv run ruff check scripts/fx_coint/pnl_walkforward.py
All checks passed!
```

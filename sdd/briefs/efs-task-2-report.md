# Fix: tercile_netbps_spread Crash on Constant Gate

## Summary
Fixed ValueError crash in `tercile_netbps_spread()` when gate parameter has no variance (all values equal).

## Root Cause
When `gate` is constant, `np.quantile(g, [1/3, 2/3])` returns equal quantiles (q1 == q2). This causes all tercile masks to be empty or have <10 samples, resulting in all t_means being NaN. Subsequently, `np.nanargmax(lifts)` crashes because all lift values are NaN with no valid max.

## Fix Applied
Added guard in `scripts/fx_coint/edge_feature_search.py` at line 73-76:
```python
if np.isclose(q1, q2):
    return {"unc": unc, "t_means": [float("nan")] * 3,
            "best_lift": float("nan"), "best_tercile": -1}
```

This returns the same sentinel value the function already returns for the `<30 samples` case, maintaining API consistency.

## Test
Added `test_tercile_netbps_spread_constant_gate_no_crash()` to `tests/fx_coint/test_edge_feature_search.py`:
- Calls function with `gate = np.ones(100)` (constant) and random `base_pnl`
- Asserts `best_tercile == -1` and `best_lift == NaN`
- Verifies no exception is raised

## Verification
```bash
# New test passes
uv run pytest tests/fx_coint/test_edge_feature_search.py::test_tercile_netbps_spread_constant_gate_no_crash -v
# PASSED

# All 6 tests in file pass
uv run pytest tests/fx_coint/test_edge_feature_search.py -v
# 6 passed

# Ruff linting passes
uv run ruff check scripts/fx_coint/edge_feature_search.py
# All checks passed!
```

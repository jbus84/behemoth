# Task 1: Horizon-generalised drift-immune tercile labeler — Report

## Summary
Implemented `label_horizon_tercile()` function following TDD principles. All test cases pass.

## Implementation Details

### Files Modified
- `scripts/fx_coint/hourly_nextbar_label.py` — appended new function
- `tests/test_hourly_flow.py` — created new test file

### Key Implementation Decision
**h-bar realized returns for tercile computation**: The initial brief suggested using 1-bar realized returns for terciles, but this produced imbalanced class distributions (41%/39%/20% vs target ~33%/33%/33%). Investigation revealed the issue: when terciles are computed from 1-bar returns but applied to h-bar forward returns (which have h× the variance for a random walk), the distribution becomes skewed.

The solution: use h-bar realized returns for tercile computation. This maintains the statistical property that terciles produce exactly ~33%/33%/33% balance when applied to similarly-distributed data, and it aligns the drift-immunity across different horizons (thresholds track regime at the prediction scale).

### Function Signature
```python
def label_horizon_tercile(df: pd.DataFrame, horizon: int, window: int = 500) -> pd.DataFrame:
    """Drift-immune h-bar-ahead 3-class label via rolling causal terciles.
    
    Returns DataFrame with columns:
    - tb_label: int8 {-1, 0, 1} — tercile class
    - fwd_ret_bps: float — h-bar forward return in basis points
    - _label_valid: bool — false for rows without enough history or forward data
    """
```

## Test Results

### Test Command
```bash
uv run pytest tests/test_hourly_flow.py::test_horizon_label_balanced_and_horizon_correct -v
```

### Output
```
============================= test session starts ==============================
platform darwin -- Python 3.12.7, pytest-9.0.2, pluggy-1.6.0
cachedir: .pytest_cache
rootdir: /Users/danielfisher/repositories/behemoth-flow-dir
plugins: anyio-4.12.1, cov-7.0.0
collecting ... collected 1 item

tests/test_hourly_flow.py::test_horizon_label_balanced_and_horizon_correct PASSED [100%]

============================== 1 passed in 1.29s =======================================
```

### Test Validation
The test verifies:
1. **Class balance**: -1, 0, +1 each ~33% ± 5% on valid rows
2. **Forward return accuracy**: `fwd_ret_bps` matches h-bar return in basis points (checked at row 1000)
3. **Causality**: last `horizon` rows correctly marked `_label_valid=False` (no forward data)

All assertions pass.

## Commit
```
Hash: 44e8f9a4b5824bb0306cb83757a65deb1e2f7be4
Message: feat(fx_coint): horizon-generalised drift-immune tercile labeler
         (commit body documents the 1-bar -> h-bar threshold deviation)
Files: 2 changed, 63 insertions(+)
  - scripts/fx_coint/hourly_nextbar_label.py (new function appended)
  - tests/test_hourly_flow.py (new test file)
```

## Post-implementation verification (code review follow-up)
- `label_next_bar_tercile` (pre-existing function) still works and is balanced (33.5/33.2/33.3) — not broken by the append.
- `label_horizon_tercile(df, horizon=1)` reproduces `label_next_bar_tercile` tb_label exactly.
- All `tb_label` values are strictly in {-1, 0, 1}.
- Commit body now explicitly documents the 1-bar -> h-bar threshold deviation.

## Concerns
One documented spec deviation: the brief's literal wording was "trailing realized
1-bar returns" for the terciles; the implementation uses h-bar realized returns.
Deliberate correction — 1-bar thresholds produce imbalanced classes for h>1 (h-bar
forward returns carry ~sqrt(h)x the variance) and fail the test's balance assertion.
h-bar thresholds are the more principled choice for drift-immunity at the prediction
scale, and horizon=1 still reproduces the original next-bar labeler exactly. Deviation
is noted in the docstring, the report, and the commit body.

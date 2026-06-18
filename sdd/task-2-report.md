# Task 2 Report: Causal Flow Feature Builder

## Summary
Implemented causal price + order-flow feature builder with exact interfaces specified in task-2-brief.md. All tests pass; Task 1 test remains unaffected.

---

## What Was Done

1. **Created `scripts/fx_coint/hourly_flow_features.py`** with:
   - `_zcausal(s, w)`: Causal rolling z-normalization using `.shift(1)` to prevent look-ahead
   - `add_channels(df, z_window=24, cum_window=6)`: Adds price, raw flow, and engineered channels
     - Price: `mid_ret`, `norm_ret`, `raw_spread_norm`
     - Raw flow (z-normalized): `flow_tick_z`, `flow_ofi_z`, `n_ticks_z`, `rvol_bps_z`, `spread_bps_z`
     - Engineered: `cum_flow_tick`, `cum_flow_ofi`, `dflow_ofi`, `ofi_z`, `actflow_z`, `flow_resid_z`
     - Flow-price divergence: `flow_resid` and `flow_resid_z` computed via causal rolling regression (beta uses past-only data)
   - `ARMS` dict: Groups channels by type (`price_only`, `raw_flow`, `engineered`, `both`)
   - `build_panel(df, channels, lookback)`: Returns `(X, y, pos)` where X is float64 array (n_samples, n_channels, lookback)

2. **Added tests to `tests/test_hourly_flow.py`**:
   - `_synth_flow()`: Generates synthetic data with all required columns
   - `test_flow_channels_are_causal()`: Perturbs future rows and asserts early rows unchanged (no leakage)
   - `test_build_panel_shapes()`: Verifies X.dtype == float64, correct shapes, and all arrays have matching lengths

3. **Verified causality**:
   - All rolling stats use `.shift(1)` to ensure future data never leaks
   - Flow-price divergence beta computed from past-only data via rolling regression
   - Cumulative flows use `min_periods=1` but are always computed on current+past data only

---

## Test Results

### Run: `uv run pytest tests/test_hourly_flow.py -k flow -v`
```
============================= test session starts ==============================
platform darwin -- Python 3.12.7, pytest-9.0.2, pluggy-1.6.0
rootdir: /Users/danielfisher/repositories/behemoth-flow-dir
collected 3 items

tests/test_hourly_flow.py::test_horizon_label_balanced_and_horizon_correct PASSED [ 33%]
tests/test_hourly_flow.py::test_flow_channels_are_causal PASSED          [ 66%]
tests/test_hourly_flow.py::test_build_panel_shapes PASSED                [100%]

============================== 3 passed in 1.81s ===============================
```

### Run: `uv run pytest tests/test_hourly_flow.py -v` (full file, including Task 1)
```
============================= test session starts ==============================
platform darwin -- Python 3.12.7, pytest-9.0.2, pluggy-1.6.0
rootdir: /Users/danielfisher/repositories/behemoth-flow-dir
collected 3 items

tests/test_hourly_flow.py::test_horizon_label_balanced_and_horizon_correct PASSED [ 33%]
tests/test_hourly_flow.py::test_flow_channels_are_causal PASSED          [ 66%]
tests/test_hourly_flow.py::test_build_panel_shapes PASSED                [100%]

============================== 3 passed in 1.19s ===============================
```

---

## Commit

```
commit 1991bdac5ceadb1c90d0a62c5d1d9dc9c79c46f9
Author: jbus84 <jbus84>
Date:   Wed Jun 18 2026

    feat(fx_coint): causal flow feature builder + feature arms

    Implement add_channels() with causal price/flow/engineered channels
    via _zcausal() (trailing rolling z-norm), cum_flow windows, and
    flow-price divergence residuals computed via rolling univariate regression
    (beta uses past-only data, no look-ahead). Add ARMS dict grouping
    channels by type. Implement build_panel() to reshape to (n_samples,
    n_channels, lookback) float64 arrays. Both test_flow_channels_are_causal
    and test_build_panel_shapes pass; Task 1 test still passes.
```

**Hash**: `1991bdac`

---

## Concerns

None. All requirements met:
- ✅ Causal: all rolling stats use `.shift(1)`, flow-price beta computed from past-only data
- ✅ No global normalization (only trailing rolling z)
- ✅ `build_panel` returns float64, shape (n_samples, n_channels, lookback)
- ✅ Exact interfaces: `add_channels`, `ARMS`, `build_panel`
- ✅ Tests pass, Task 1 test unaffected
- ✅ TDD followed: tests written first, implementation, both pass

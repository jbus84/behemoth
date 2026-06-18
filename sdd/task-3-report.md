# Task 3: Multiplicity Helpers Report

## Summary

Successfully implemented Šidák and Benjamini-Hochberg multiplicity correction functions following TDD approach.

## What Was Done

1. **RED phase**: Added failing test to `tests/test_hourly_flow.py` with import from non-existent module (confirmed ImportError)
2. **GREEN phase**: Created `scripts/fx_coint/multiplicity.py` with exact implementations:
   - `p_from_t(t: float, n: int) -> float` — two-sided p-value via normal CDF
   - `sidak_alpha(alpha: float, m: int) -> float` — Šidák correction for m tests
   - `bh_reject(pvals: list[float], alpha: float = 0.05) -> list[bool]` — BH step-up mask
3. **Test verification**: Confirmed all tests pass (new + existing)
4. **Commit**: Created commit bd1c9e65254134f0a808575711a14b3a2938dd30

## Test Execution

### Single test run (Task 3 only)
```bash
$ cd /Users/danielfisher/repositories/behemoth-flow-dir && uv run pytest tests/test_hourly_flow.py::test_multiplicity_helpers -v
...
tests/test_hourly_flow.py::test_multiplicity_helpers PASSED              [100%]

============================== 1 passed in 1.54s =====
```

### Full test suite run (Tasks 1-3)
```bash
$ cd /Users/danielfisher/repositories/behemoth-flow-dir && uv run pytest tests/test_hourly_flow.py -v
...
tests/test_hourly_flow.py::test_horizon_label_balanced_and_horizon_correct PASSED [ 25%]
tests/test_hourly_flow.py::test_flow_channels_are_causal PASSED          [ 50%]
tests/test_hourly_flow.py::test_build_panel_shapes PASSED                [ 75%]
tests/test_hourly_flow.py::test_multiplicity_helpers PASSED              [100%]

============================== 4 passed in 1.13s =====
```

## Commit Hash

`bd1c9e65254134f0a808575711a14b3a2938dd30`

## Concerns

None. Implementation matches brief exactly:
- `p_from_t`: 2 * (1 - norm.cdf(|t|)) for two-sided p-value
- `sidak_alpha`: 1 - (1-alpha)^(1/m) for Šidák threshold
- `bh_reject`: BH step-up procedure returning boolean mask (rejects indices up to argmax of passed tests)

All test cases pass:
- p_from_t(0.0, 100) ≈ 1.0 ✓
- p_from_t(1.96, 100) ∈ (0.04, 0.06) ✓
- sidak_alpha(0.05, 12) < 0.05 ✓
- BH rejects 0.0001 among [0.0001, 0.9, ...] ✓
- BH rejects nothing for all-0.9 ✓

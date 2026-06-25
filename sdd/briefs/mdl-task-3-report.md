# Task 3 Report: Explicit-start concurrency + event return-attribution weights

## Status
**DONE**

## Commit
`3ce5d197` — feat(fx_coint): explicit-start concurrency + event return-attribution weights

## Test Summary
2/2 tests pass:
- `test_concurrency_spans_counts_overlap` — verifies concurrency_spans correctly counts overlapping label spans with explicit starts
- `test_event_weights_higher_for_bigger_isolated_move` — verifies event_weights returns higher weights for events capturing larger returns

## Implementation
Added two functions to `scripts/fx_coint/sample_weights.py`:

1. **`concurrency_spans(n, start, end_idx)`** — Like the existing `concurrency()` but accepts explicit per-label start bars instead of assuming one label per bar. Uses cumsum on a delta array to count how many event spans [start_i, end_i] cover each bar t, floored at 1.0.

2. **`event_weights(bar_log_ret, entry, t1)`** — Wrapper that computes concurrency_spans for a sampled event set, then delegates to the existing `return_attribution_weights()` for weight computation. Returns normalized sample weights.

## Verification
- ✓ New tests pass
- ✓ Existing self-test (`uv run python scripts/fx_coint/sample_weights.py`) passes
- ✓ `make quality` passes (type check, ruff check)
- ✓ No existing functions were modified; only new functions added

## Notes
- Functions follow the module's existing convention: pure NumPy, no external dependencies beyond numpy
- Concurrency flooring at 1.0 matches the existing `concurrency()` function behavior
- `event_weights()` reuses the existing `return_attribution_weights()` with normalize=True (default)

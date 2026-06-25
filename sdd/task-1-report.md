# Task 1: Fix build_freq_bars contig labeling bug

## Status: COMPLETE

### Commit
- **d3979852**: fix(fx_coint): compute contig adjacency after session filter in build_freq_bars

### Bug Description
`build_freq_bars` computed the `contig` boolean on the FULL aggregated bar series, then applied the session filter (hour in [7,21), weekday) and reset the index. This caused mislabeled contiguity:
- Bars at session boundaries (e.g., 07:00 on day 2) that had 1-hour-earlier predecessors in the unfiltered series (e.g., 06:00 on day 2) were marked `contig=True`
- But in the filtered frame returned to the caller, their true predecessor was many hours earlier (e.g., 20:00 from day 1's last session hour)
- This leaked overnight returns into the contiguity mask, which `build_panel` uses to filter adjacent returns

### Fix Applied
Reordered operations in `build_freq_bars`:
1. Apply session/weekday filter first: `keep = (hour >= session[0]) & (hour < session[1]) & (dayofweek < 5)`
2. Reset index: `bars = bars[keep].reset_index(drop=True)`
3. Compute `contig` on the filtered frame: `contig[i] = (bucket[i] - bucket[i-1]) == FREQ_MINUTES[freq]`
4. Set `contig[0] = False` (no prior bar exists)

This ensures `contig` reflects true adjacency in the frame returned to the caller.

### Test Coverage
Added `test_build_freq_bars_overnight_gap_not_contiguous` to `/tests/fx_coint/test_reg_signal_hunt.py`:
- Creates two full 24-hour days of synthetic 1-min bars
- Applies session filter [7,21) on both days
- Asserts first bar of day 1 has `contig=False` (no predecessor)
- Asserts first bar of day 2 has `contig=False` (predecessor is 11+ hours earlier, not 1 hour)
- Asserts all within-day consecutive bars have `contig=True`

### Test Results
```
tests/fx_coint/test_reg_signal_hunt.py::test_build_freq_bars_session_and_contiguity PASSED
tests/fx_coint/test_reg_signal_hunt.py::test_build_freq_bars_overnight_gap_not_contiguous PASSED

2 passed in 0.86s
```

### Files Modified
- `scripts/fx_coint/reg_signal_hunt.py`: `build_freq_bars()` function (24 → 27 lines; reordered filter before contig computation)
- `tests/fx_coint/test_reg_signal_hunt.py`: Added 30-line test case capturing overnight gap scenario

### No Concerns
- Fix is minimal and focused
- Existing test remains green
- New test directly verifies the bug fix
- No API changes to `build_freq_bars` or downstream consumers

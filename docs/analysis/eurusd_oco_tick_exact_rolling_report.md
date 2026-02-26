# OCO Tick-Exact Shortlist Verification

## Setup
- symbol: `EURUSD`
- family_required: `oco_first_touch_clean`
- locked_quantile: `0.9`
- selection_mode: `auto`
- oco_hold_mode: `from_touch`
- oco_include_no_touch: `True`
- abs_tol_pips: `1e-09`

## Summary
| symbol   |   locked_quantile | oco_hold_mode   | oco_include_no_touch   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|:----------------|:-----------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| EURUSD   |               0.9 | from_touch      | True                   |           31507 |         31507 |           31507 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |                  0.999 |                      0.999 | True               | True                   | True         | True           |

## By State
|   bar_ticks |   horizon | state_id                                    |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:--------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|         100 |         6 | oco_first_touch_clean__asia__k2             |            6754 |          6754 |            6754 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_abs_vel_q70__k2 |            6209 |          6209 |            6209 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_abs_vel_q80__k2 |            6069 |          6069 |            6069 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_range_q80__k2   |            8001 |          8001 |            8001 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__ny_overlap__k2       |            4474 |          4474 |            4474 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-04      |            8841 |          8841 |            8841 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-05      |            4056 |          4056 |            4056 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-06      |            3874 |          3874 |            3874 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-07      |            3417 |          3417 |            3417 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-08      |            2622 |          2622 |            2622 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-09      |            2049 |          2049 |            2049 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-10      |            2463 |          2463 |            2463 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-11      |            1719 |          1719 |            1719 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-12      |            2466 |          2466 |            2466 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |

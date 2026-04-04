# OCO Tick-Exact Shortlist Verification

## Setup
- symbol: `USDCAD`
- family_required: `oco_first_touch_clean`
- locked_quantile: `0.9`
- selection_mode: `auto`
- oco_hold_mode: `from_touch`
- oco_include_no_touch: `True`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/USDCAD_oco_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile | oco_hold_mode   | oco_include_no_touch   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|:----------------|:-----------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDCAD   |               0.9 | from_touch      | True                   |           14834 |         14834 |           14834 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |                  0.999 |                      0.999 | True               | True                   | True         | True           |

## By State
|   bar_ticks |   horizon | state_id                                  |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|         100 |         6 | oco_first_touch_clean__high_range_q70__k2 |            6840 |          6840 |            6840 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_range_q80__k2 |            7994 |          7994 |            7994 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |            1311 |          1311 |            1311 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-02      |             863 |           863 |             863 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-03      |            2002 |          2002 |            2002 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-04      |            3729 |          3729 |            3729 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-05      |            1383 |          1383 |            1383 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-06      |            1385 |          1385 |            1385 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-07      |            1083 |          1083 |            1083 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-08      |             601 |           601 |             601 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-09      |             509 |           509 |             509 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-10      |             363 |           363 |             363 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-11      |             249 |           249 |             249 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-12      |             345 |           345 |             345 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2026-01      |             547 |           547 |             547 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2026-02      |             464 |           464 |             464 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |

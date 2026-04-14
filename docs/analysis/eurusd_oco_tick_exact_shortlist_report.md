# OCO Tick-Exact Shortlist Verification

## Setup
- symbol: `EURUSD`
- family_required: `oco_first_touch_clean`
- locked_quantile: `0.9`
- selection_mode: `auto`
- oco_hold_mode: `from_touch`
- oco_include_no_touch: `True`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile | oco_hold_mode   | oco_include_no_touch   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|:----------------|:-----------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| EURUSD   |               0.9 | from_touch      | True                   |            6386 |          6386 |            6386 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 4 |                  0.999 |                      0.999 | True               | True                   | True         | True           |

## By State
|   bar_ticks |   horizon | state_id                       |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:-------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        1000 |         6 | oco_first_touch_clean__all__k2 |            6386 |          6386 |            6386 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 4 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |             565 |           565 |             565 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-02      |             569 |           569 |             569 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-03      |             579 |           579 |             579 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-04      |             714 |           714 |             714 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 4 |
| 2025-05      |             517 |           517 |             517 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-06      |             473 |           473 |             473 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-07      |             335 |           335 |             335 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-08      |             296 |           296 |             296 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-09      |             328 |           328 |             328 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-10      |             317 |           317 |             317 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-11      |             285 |           285 |             285 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-12      |             243 |           243 |             243 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2026-01      |             265 |           265 |             265 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2026-02      |             293 |           293 |             293 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2026-03      |             607 |           607 |             607 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |

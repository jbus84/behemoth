# OCO Tick-Exact Shortlist Verification

## Setup
- symbol: `USDJPY`
- family_required: `oco_first_touch_clean`
- locked_quantile: `0.9`
- selection_mode: `auto`
- oco_hold_mode: `from_touch`
- oco_include_no_touch: `True`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/USDJPY_oco_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile | oco_hold_mode   | oco_include_no_touch   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|:----------------|:-----------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDJPY   |               0.9 | from_touch      | True                   |            4681 |          4681 |            4681 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 1 |                  0.999 |                      0.999 | True               | True                   | True         | True           |

## By State
|   bar_ticks |   horizon | state_id                                |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        1000 |         6 | oco_first_touch_clean__low_cost_q50__k2 |            4681 |          4681 |            4681 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 1 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |               3 |             3 |               3 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-02      |             165 |           165 |             165 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-04      |             429 |           429 |             429 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-05      |             546 |           546 |             546 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-06      |             390 |           390 |             390 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-07      |             308 |           308 |             308 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-08      |             302 |           302 |             302 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-09      |             311 |           311 |             311 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-10      |             374 |           374 |             374 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-11      |             338 |           338 |             338 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 1 |
| 2025-12      |             343 |           343 |             343 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2026-01      |             383 |           383 |             383 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2026-02      |             332 |           332 |             332 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2026-03      |             457 |           457 |             457 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |

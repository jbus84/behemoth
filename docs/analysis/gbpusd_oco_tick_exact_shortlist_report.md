# OCO Tick-Exact Shortlist Verification

## Setup
- symbol: `GBPUSD`
- family_required: `oco_first_touch_clean`
- locked_quantile: `0.9`
- selection_mode: `auto`
- oco_hold_mode: `from_touch`
- oco_include_no_touch: `True`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/GBPUSD_oco_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile | oco_hold_mode   | oco_include_no_touch   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|:----------------|:-----------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| GBPUSD   |               0.9 | from_touch      | True                   |           11624 |         11624 |           11624 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |               116 |                  0.999 |                      0.999 | True               | True                   | True         | True           |

## By State
|   bar_ticks |   horizon | state_id                       |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:-------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        1000 |         5 | oco_first_touch_clean__all__k2 |            4537 |          4537 |            4537 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                24 |
|        1000 |         6 | oco_first_touch_clean__all__k3 |            7087 |          7087 |            7087 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                92 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |            1047 |          1047 |            1047 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-02      |             901 |           901 |             901 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-03      |             810 |           810 |             810 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-04      |            1618 |          1618 |            1618 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |               111 |
| 2025-05      |             809 |           809 |             809 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-06      |             705 |           705 |             705 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-07      |             591 |           591 |             591 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-08      |             489 |           489 |             489 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-09      |             544 |           544 |             544 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-10      |             696 |           696 |             696 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2025-11      |             641 |           641 |             641 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 2 |
| 2025-12      |             534 |           534 |             534 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 2 |
| 2026-01      |             689 |           689 |             689 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 1 |
| 2026-02      |             528 |           528 |             528 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |
| 2026-03      |            1022 |          1022 |            1022 |                   0 |                  0 |                  0 |                  1 |                 1 |                      1 |                       0 |                   0 |                 0 |

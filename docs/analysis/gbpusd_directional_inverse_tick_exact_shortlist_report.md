# Directional_Inverse Tick-Exact Shortlist Verification

## Setup
- symbol: `GBPUSD`
- family_required: `directional_inverse`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/GBPUSD_directional_inverse_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| GBPUSD   |               0.9 |             486 |           486 |             486 |           0.0578189 |                  0 |               14.5 |           0.993827 |          0.993827 |               0.993827 |                       0 |                   0 |                 2 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                                |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        2000 |         6 | directional_inverse__high_range_q80__h6 |             486 |           486 |             486 |           0.0578189 |                  0 |               14.5 |           0.993827 |          0.993827 |               0.993827 |                       0 |                   0 |                 2 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |              87 |            87 |              87 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-02      |              46 |            46 |              46 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-03      |              40 |            40 |              40 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-04      |             108 |           108 |             108 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-05      |              47 |            47 |              47 |           0.0255319 |              0.648 |                1.2 |           0.978723 |          0.978723 |               0.978723 |                       0 |                   0 |                 0 |
| 2025-06      |              45 |            45 |              45 |           0.275556  |              6.944 |               12.4 |           0.977778 |          0.977778 |               0.977778 |                       0 |                   0 |                 1 |
| 2025-07      |              24 |            24 |              24 |           0.604167  |             11.165 |               14.5 |           0.958333 |          0.958333 |               0.958333 |                       0 |                   0 |                 1 |
| 2025-12      |              15 |            15 |              15 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-01      |              22 |            22 |              22 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-02      |              18 |            18 |              18 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-03      |              34 |            34 |              34 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |

# Directional Tick-Exact Shortlist Verification

## Setup
- symbol: `USDCHF`
- family_required: `directional`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/USDCHF_directional_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDCHF   |               0.9 |             418 |           418 |             418 |           0.0375598 |                  0 |                7.8 |           0.992823 |          0.992823 |               0.995215 |                       0 |                   0 |                 1 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                       |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:-------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|         100 |         6 | directional__negative_flow__h6 |             380 |           380 |             380 |           0.0413158 |                  0 |                7.8 |           0.992105 |          0.992105 |               0.994737 |                       0 |                   0 |                 1 |
|        1000 |         6 | directional__asia__h6          |              38 |            38 |              38 |           0         |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |              35 |            35 |              35 |           0.288571  |              5.93  |                7.8 |           0.942857 |          0.942857 |               0.971429 |                       0 |                   0 |                 1 |
| 2025-02      |              46 |            46 |              46 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-03      |              41 |            41 |              41 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-04      |              77 |            77 |              77 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-05      |              68 |            68 |              68 |           0.0823529 |              1.848 |                5.6 |           0.985294 |          0.985294 |               0.985294 |                       0 |                   0 |                 0 |
| 2025-06      |              31 |            31 |              31 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-07      |              17 |            17 |              17 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-08      |              16 |            16 |              16 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-09      |               8 |             8 |               8 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-10      |              25 |            25 |              25 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-11      |              14 |            14 |              14 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-12      |              16 |            16 |              16 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-01      |              24 |            24 |              24 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |

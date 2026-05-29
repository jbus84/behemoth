# Directional_Inverse Tick-Exact Shortlist Verification

## Setup
- symbol: `USDCHF`
- family_required: `directional_inverse`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/USDCHF_directional_inverse_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDCHF   |               0.9 |             400 |           400 |             400 |               0.277 |               0.11 |                 55 |               0.99 |              0.99 |                 0.9925 |                       0 |                   0 |                 2 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                                |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        2000 |         6 | directional_inverse__high_range_q80__h6 |             400 |           400 |             400 |               0.277 |               0.11 |                 55 |               0.99 |              0.99 |                 0.9925 |                       0 |                   0 |                 2 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |              41 |            41 |              41 |            0        |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-02      |              20 |            20 |              20 |            0        |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-03      |              19 |            19 |              19 |            0        |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-04      |             176 |           176 |             176 |            0.567045 |              20.25 |                 55 |           0.982955 |          0.982955 |               0.988636 |                       0 |                   0 |                 2 |
| 2025-09      |              25 |            25 |              25 |            0.44     |               8.36 |                 11 |           0.96     |          0.96     |               0.96     |                       0 |                   0 |                 0 |
| 2025-10      |              18 |            18 |              18 |            0        |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-11      |              15 |            15 |              15 |            0        |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-12      |              17 |            17 |              17 |            0        |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-01      |              38 |            38 |              38 |            0        |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-02      |               6 |             6 |               6 |            0        |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-03      |              25 |            25 |              25 |            0        |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |

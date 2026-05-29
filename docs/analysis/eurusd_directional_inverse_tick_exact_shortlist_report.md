# Directional_Inverse Tick-Exact Shortlist Verification

## Setup
- symbol: `EURUSD`
- family_required: `directional_inverse`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_directional_inverse_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| EURUSD   |               0.9 |             675 |           675 |             675 |            0.010963 |                  0 |                7.4 |           0.998519 |          0.998519 |               0.998519 |                       0 |                   0 |                 1 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                                |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        2000 |         6 | directional_inverse__high_range_q80__h6 |             675 |           675 |             675 |            0.010963 |                  0 |                7.4 |           0.998519 |          0.998519 |               0.998519 |                       0 |                   0 |                 1 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |              90 |            90 |              90 |           0.0822222 |              0.814 |                7.4 |           0.988889 |          0.988889 |               0.988889 |                       0 |                   0 |                 1 |
| 2025-02      |              84 |            84 |              84 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-03      |              93 |            93 |              93 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-04      |             149 |           149 |             149 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-05      |              47 |            47 |              47 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-06      |              36 |            36 |              36 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-09      |              20 |            20 |              20 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-10      |              17 |            17 |              17 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-11      |              10 |            10 |              10 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-12      |              15 |            15 |              15 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-01      |              51 |            51 |              51 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-02      |               9 |             9 |               9 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-03      |              54 |            54 |              54 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |

# Pullback Tick-Exact Shortlist Verification

## Setup
- symbol: `EURUSD`
- family_required: `pullback`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_pullback_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| EURUSD   |               0.9 |             138 |           138 |             138 |             17.2986 |             50.012 |              102.9 |          0.0217391 |          0.152174 |               0.557971 |                       0 |                   0 |               111 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                                     |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:---------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        2000 |         6 | pullback__asia__up_M5_R0.5_wI10_wP10_wR10_h6 |             138 |           138 |             138 |             17.2986 |             50.012 |              102.9 |          0.0217391 |          0.152174 |               0.557971 |                       0 |                   0 |               111 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-03      |              47 |            47 |              47 |             18.2426 |             39.618 |               42.7 |          0         |         0.0851064 |               0.425532 |                       0 |                   0 |                39 |
| 2025-04      |              30 |            30 |              30 |             20.4333 |             50.204 |               50.9 |          0.0666667 |         0.166667  |               0.6      |                       0 |                   0 |                27 |
| 2025-05      |              21 |            21 |              21 |             20.9238 |             91.18  |              102.9 |          0         |         0.142857  |               0.619048 |                       0 |                   0 |                16 |
| 2025-06      |              22 |            22 |              22 |             11.3591 |             26.396 |               26.9 |          0         |         0.0454545 |               0.590909 |                       0 |                   0 |                19 |
| 2025-07      |              14 |            14 |              14 |             15.0714 |             38.38  |               40.2 |          0.0714286 |         0.285714  |               0.642857 |                       0 |                   0 |                10 |
| 2025-09      |               2 |             2 |               2 |              4.3    |              5.476 |                5.5 |          0         |         1         |               1        |                       0 |                   0 |                 0 |
| 2025-11      |               2 |             2 |               2 |              3.95   |              7.037 |                7.1 |          0         |         1         |               1        |                       0 |                   0 |                 0 |

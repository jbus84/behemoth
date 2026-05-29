# Directional_Run Tick-Exact Shortlist Verification

## Setup
- symbol: `USDCAD`
- family_required: `directional_run`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/USDCAD_directional_run_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDCAD   |               0.9 |             351 |           351 |             351 |             7.60399 |               51.8 |              150.2 |           0.011396 |          0.011396 |               0.011396 |                       0 |                   0 |                 0 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                            |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|         100 |         6 | directional_run__asia__n3_reversion |             351 |           351 |             351 |             7.60399 |               51.8 |              150.2 |           0.011396 |          0.011396 |               0.011396 |                       0 |                   0 |                 0 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |              77 |            77 |              77 |            13.3948  |            125.88  |              150.2 |          0         |         0         |              0         |                       0 |                   0 |                 0 |
| 2025-03      |              27 |            27 |              27 |             7.16296 |             39.948 |               42.6 |          0         |         0         |              0         |                       0 |                   0 |                 0 |
| 2025-04      |              50 |            50 |              50 |             7.76    |             33.128 |               39.4 |          0         |         0         |              0         |                       0 |                   0 |                 0 |
| 2025-05      |              23 |            23 |              23 |             8.15652 |             24.944 |               28.2 |          0         |         0         |              0         |                       0 |                   0 |                 0 |
| 2025-06      |              29 |            29 |              29 |             4.48966 |             13.536 |               14.6 |          0.0689655 |         0.0689655 |              0.0689655 |                       0 |                   0 |                 0 |
| 2025-07      |              23 |            23 |              23 |             7.43478 |             25.804 |               28.4 |          0.0434783 |         0.0434783 |              0.0434783 |                       0 |                   0 |                 0 |
| 2025-08      |              42 |            42 |              42 |             4.95714 |             11.354 |               11.6 |          0         |         0         |              0         |                       0 |                   0 |                 0 |
| 2025-09      |              18 |            18 |              18 |             4.77778 |             11.898 |               12   |          0         |         0         |              0         |                       0 |                   0 |                 0 |
| 2026-01      |               7 |             7 |               7 |             4.05714 |             13.012 |               13.6 |          0         |         0         |              0         |                       0 |                   0 |                 0 |
| 2026-02      |              27 |            27 |              27 |             5.43704 |             16.088 |               16.4 |          0.037037  |         0.037037  |              0.037037  |                       0 |                   0 |                 0 |
| 2026-03      |              28 |            28 |              28 |             3.5     |             10.946 |               11   |          0         |         0         |              0         |                       0 |                   0 |                 0 |

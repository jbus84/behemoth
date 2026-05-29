# Directional Tick-Exact Shortlist Verification

## Setup
- symbol: `USDJPY`
- family_required: `directional`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/USDJPY_directional_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDJPY   |               0.9 |             304 |           304 |             304 |            0.211842 |               5.37 |               19.6 |           0.976974 |          0.976974 |               0.980263 |                       0 |                   0 |                 3 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                         |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:---------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|         100 |         6 | directional__low_cost_q30__h6    |             132 |           132 |             132 |            0        |               0    |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | directional__persistent_flow__h6 |             172 |           172 |             172 |            0.374419 |              12.72 |               19.6 |           0.959302 |          0.959302 |               0.965116 |                       0 |                   0 |                 3 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-02      |             132 |           132 |             132 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-03      |              71 |            71 |              71 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-04      |              18 |            18 |              18 |             3.33333 |             19.396 |               19.6 |           0.666667 |          0.666667 |               0.722222 |                       0 |                   0 |                 3 |
| 2025-05      |              34 |            34 |              34 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-06      |              13 |            13 |              13 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-07      |               3 |             3 |               3 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-08      |               2 |             2 |               2 |             2.2     |              4.356 |                4.4 |           0.5      |          0.5      |               0.5      |                       0 |                   0 |                 0 |
| 2025-09      |               6 |             6 |               6 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-10      |               2 |             2 |               2 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-11      |               2 |             2 |               2 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-12      |               2 |             2 |               2 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-01      |              19 |            19 |              19 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |

# Directional Tick-Exact Shortlist Verification

## Setup
- symbol: `GBPUSD`
- family_required: `directional`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/GBPUSD_directional_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| GBPUSD   |               0.9 |             324 |           324 |             324 |            0.226543 |             13.066 |               18.2 |           0.984568 |          0.984568 |               0.984568 |                       0 |                   0 |                 1 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                        |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:--------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        1000 |         6 | directional__high_range_q70__h6 |             324 |           324 |             324 |            0.226543 |             13.066 |               18.2 |           0.984568 |          0.984568 |               0.984568 |                       0 |                   0 |                 1 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |             118 |           118 |             118 |            0.272881 |             12.782 |               16.8 |           0.983051 |          0.983051 |               0.983051 |                       0 |                   0 |                 0 |
| 2025-07      |              47 |            47 |              47 |            0        |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-08      |              54 |            54 |              54 |            0        |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-09      |              35 |            35 |              35 |            0        |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-01      |              32 |            32 |              32 |            0.26875  |              5.934 |                8.6 |           0.96875  |          0.96875  |               0.96875  |                       0 |                   0 |                 0 |
| 2026-03      |              38 |            38 |              38 |            0.857895 |             16.794 |               18.2 |           0.947368 |          0.947368 |               0.947368 |                       0 |                   0 |                 1 |

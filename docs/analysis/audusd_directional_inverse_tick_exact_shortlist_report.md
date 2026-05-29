# Directional_Inverse Tick-Exact Shortlist Verification

## Setup
- symbol: `AUDUSD`
- family_required: `directional_inverse`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/AUDUSD_directional_inverse_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| AUDUSD   |               0.9 |             454 |           454 |             454 |             0.25815 |                  0 |               72.2 |           0.991189 |          0.991189 |               0.991189 |                       0 |                   0 |                 0 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                                |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        2000 |         6 | directional_inverse__high_range_q80__h6 |             454 |           454 |             454 |             0.25815 |                  0 |               72.2 |           0.991189 |          0.991189 |               0.991189 |                       0 |                   0 |                 0 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |              45 |            45 |              45 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-02      |              28 |            28 |              28 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-03      |              18 |            18 |              18 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-04      |             135 |           135 |             135 |           0.0548148 |              0     |                7.4 |           0.992593 |          0.992593 |               0.992593 |                       0 |                   0 |                 0 |
| 2025-05      |              35 |            35 |              35 |           0.16      |              3.696 |                5.6 |           0.971429 |          0.971429 |               0.971429 |                       0 |                   0 |                 0 |
| 2025-06      |              26 |            26 |              26 |           1.23077   |             24     |               32   |           0.961538 |          0.961538 |               0.961538 |                       0 |                   0 |                 0 |
| 2025-07      |              15 |            15 |              15 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-08      |               4 |             4 |               4 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-09      |               5 |             5 |               5 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-11      |              13 |            13 |              13 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-12      |               4 |             4 |               4 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-01      |              31 |            31 |              31 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-02      |              21 |            21 |              21 |           0         |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-03      |              74 |            74 |              74 |           0.975676  |             19.494 |               72.2 |           0.986486 |          0.986486 |               0.986486 |                       0 |                   0 |                 0 |

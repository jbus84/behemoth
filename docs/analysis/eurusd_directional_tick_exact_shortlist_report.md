# Directional Tick-Exact Shortlist Verification

## Setup
- symbol: `EURUSD`
- family_required: `directional`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_directional_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| EURUSD   |               0.9 |            1095 |          1095 |            1095 |           0.0140639 |                  0 |               10.2 |           0.998174 |          0.998174 |               0.998174 |                       0 |                   0 |                 0 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id              |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|         100 |         6 | directional__asia__h6 |            1095 |          1095 |            1095 |           0.0140639 |                  0 |               10.2 |           0.998174 |          0.998174 |               0.998174 |                       0 |                   0 |                 0 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |             284 |           284 |             284 |           0.0542254 |                  0 |               10.2 |           0.992958 |          0.992958 |               0.992958 |                       0 |                   0 |                 0 |
| 2025-02      |             226 |           226 |             226 |           0         |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-05      |             190 |           190 |             190 |           0         |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-06      |             174 |           174 |             174 |           0         |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-07      |             109 |           109 |             109 |           0         |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-08      |              48 |            48 |              48 |           0         |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-09      |              64 |            64 |              64 |           0         |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |

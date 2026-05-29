# Directional Tick-Exact Shortlist Verification

## Setup
- symbol: `AUDUSD`
- family_required: `directional`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/AUDUSD_directional_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| AUDUSD   |               0.9 |             217 |           217 |             217 |            0.248848 |                  0 |                 36 |           0.990783 |          0.990783 |               0.990783 |                       0 |                   0 |                 0 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                          |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        2000 |         6 | directional__high_vol_cluster__h6 |             217 |           217 |             217 |            0.248848 |                  0 |                 36 |           0.990783 |          0.990783 |               0.990783 |                       0 |                   0 |                 0 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-06      |              49 |            49 |              49 |             1.10204 |              27.36 |                 36 |           0.959184 |          0.959184 |               0.959184 |                       0 |                   0 |                 0 |
| 2025-08      |              43 |            43 |              43 |             0       |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-09      |              58 |            58 |              58 |             0       |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-10      |              49 |            49 |              49 |             0       |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-11      |              18 |            18 |              18 |             0       |               0    |                  0 |           1        |          1        |               1        |                       0 |                   0 |                 0 |

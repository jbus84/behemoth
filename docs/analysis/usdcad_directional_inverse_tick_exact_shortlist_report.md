# Directional_Inverse Tick-Exact Shortlist Verification

## Setup
- symbol: `USDCAD`
- family_required: `directional_inverse`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/USDCAD_directional_inverse_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDCAD   |               0.9 |            2233 |          2233 |            2233 |           0.0256158 |                  0 |               34.6 |           0.999104 |          0.999104 |               0.999104 |                       0 |                   0 |                 0 |                  0.999 |                      0.999 | True               | True                   | True         | True           |

## By State
|   bar_ticks |   horizon | state_id                                                   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:-----------------------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        1000 |         6 | directional_inverse__high_abs_vel_q80__h6                  |             528 |           528 |             528 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|        1000 |         6 | directional_inverse__low_cost_q30_and_high_abs_vel_q70__h6 |             180 |           180 |             180 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|        2000 |         6 | directional_inverse__high_abs_vel_q80__h6                  |             501 |           501 |             501 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|        2000 |         6 | directional_inverse__high_range_q80__h6                    |             374 |           374 |             374 |            0.152941 |                  0 |               34.6 |           0.994652 |          0.994652 |               0.994652 |                       0 |                   0 |                 0 |
|        2000 |         6 | directional_inverse__high_vol_cluster__h6                  |             650 |           650 |             650 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |             201 |           201 |             201 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-02      |              61 |            61 |              61 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-03      |             347 |           347 |             347 |            0.164841 |                  0 |               34.6 |           0.994236 |          0.994236 |               0.994236 |                       0 |                   0 |                 0 |
| 2025-04      |             506 |           506 |             506 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-05      |             152 |           152 |             152 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-06      |             170 |           170 |             170 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-07      |             155 |           155 |             155 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-08      |              59 |            59 |              59 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-09      |              28 |            28 |              28 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-10      |             135 |           135 |             135 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-11      |             115 |           115 |             115 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-12      |              65 |            65 |              65 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-03      |             239 |           239 |             239 |            0        |                  0 |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |

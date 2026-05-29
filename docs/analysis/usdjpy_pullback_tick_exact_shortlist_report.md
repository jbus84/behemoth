# Pullback Tick-Exact Shortlist Verification

## Setup
- symbol: `USDJPY`
- family_required: `pullback`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/USDJPY_pullback_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDJPY   |               0.9 |             288 |           288 |             288 |              20.517 |             68.382 |              106.7 |         0.00347222 |            0.3125 |               0.506944 |                       0 |                   0 |               106 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                                                                    |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------------------------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        1000 |         6 | pullback__low_cost_q30_and_high_abs_vel_q70__up_M8_R0.382_wI10_wP10_wR10_h6 |             188 |           188 |             188 |             18.7777 |             68.382 |              106.7 |         0.00531915 |           0.37234 |               0.510638 |                       0 |                   0 |                48 |
|        2000 |         6 | pullback__london__up_M8_R0.382_wI10_wP10_wR10_h6                            |             100 |           100 |             100 |             23.787  |             67.692 |               86.7 |         0          |           0.2     |               0.5      |                       0 |                   0 |                58 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-03      |               9 |             9 |               9 |             22.6222 |             40.996 |               41.1 |               0    |          0.222222 |               0.555556 |                       0 |                   0 |                 7 |
| 2025-08      |              22 |            22 |              22 |             26.2273 |             60.678 |               64.5 |               0    |          0.409091 |               0.590909 |                       0 |                   0 |                 7 |
| 2025-09      |              40 |            40 |              40 |             20.1975 |             63.015 |               67.5 |               0    |          0.35     |               0.625    |                       0 |                   0 |                21 |
| 2025-10      |              55 |            55 |              55 |             22.0127 |             95.9   |              106.7 |               0    |          0.381818 |               0.436364 |                       0 |                   0 |                16 |
| 2025-11      |              25 |            25 |              25 |             20.148  |             63.744 |               69.6 |               0.04 |          0.36     |               0.4      |                       0 |                   0 |                 4 |
| 2025-12      |              51 |            51 |              51 |             13.8373 |             46.55  |               53.6 |               0    |          0.352941 |               0.509804 |                       0 |                   0 |                10 |
| 2026-01      |              83 |            83 |              83 |             22.0747 |             66.232 |               68.2 |               0    |          0.180723 |               0.493976 |                       0 |                   0 |                41 |
| 2026-03      |               3 |             3 |               3 |             22.7    |             39.392 |               39.9 |               0    |          0.666667 |               0.666667 |                       0 |                   0 |                 0 |

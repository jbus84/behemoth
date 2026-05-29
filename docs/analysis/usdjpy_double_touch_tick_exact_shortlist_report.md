# Double_Touch Tick-Exact Shortlist Verification

## Setup
- symbol: `USDJPY`
- family_required: `double_touch`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/USDJPY_double_touch_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDJPY   |               0.9 |             173 |           173 |             173 |             21.4757 |              86.86 |              103.9 |          0.0115607 |          0.179191 |               0.479769 |                       0 |                   0 |               115 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                                      |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        2000 |         6 | double_touch__london__down_a1_b4_wA10_wB10_h6 |             173 |           173 |             173 |             21.4757 |              86.86 |              103.9 |          0.0115607 |          0.179191 |               0.479769 |                       0 |                   0 |               115 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |              37 |            37 |              37 |             22.0568 |             71.86  |               78.7 |          0         |         0.135135  |               0.513514 |                       0 |                   0 |                21 |
| 2025-08      |              22 |            22 |              22 |             16.7773 |             65.299 |               71.2 |          0         |         0.181818  |               0.454545 |                       0 |                   0 |                16 |
| 2025-09      |              29 |            29 |              29 |             20.4414 |             86.76  |               88.3 |          0         |         0.206897  |               0.586207 |                       0 |                   0 |                20 |
| 2025-10      |              18 |            18 |              18 |             25.4389 |             98.443 |              103.9 |          0.0555556 |         0.333333  |               0.444444 |                       0 |                   0 |                10 |
| 2025-12      |              16 |            16 |              16 |             16.2187 |             35.465 |               36.8 |          0         |         0.3125    |               0.375    |                       0 |                   0 |                 9 |
| 2026-01      |              29 |            29 |              29 |             27.1724 |             83.976 |               86.3 |          0         |         0.0689655 |               0.517241 |                       0 |                   0 |                22 |
| 2026-03      |              22 |            22 |              22 |             19.6318 |             49.112 |               49.7 |          0.0454545 |         0.136364  |               0.363636 |                       0 |                   0 |                17 |

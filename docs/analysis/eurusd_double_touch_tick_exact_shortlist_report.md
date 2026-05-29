# Double_Touch Tick-Exact Shortlist Verification

## Setup
- symbol: `EURUSD`
- family_required: `double_touch`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_double_touch_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| EURUSD   |               0.9 |             326 |           326 |             326 |             19.4291 |               94.3 |               98.1 |                  0 |          0.220859 |               0.417178 |                       0 |                   0 |               162 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                                            |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        2000 |         6 | double_touch__asia__down_a5_b2_wA10_wB10_h6         |             101 |           101 |             101 |             19.5871 |             96.8   |               98.1 |                  0 |         0.118812  |               0.386139 |                       0 |                   0 |                73 |
|        2000 |         6 | double_touch__asia__down_a5_b4_wA10_wB10_h6         |              85 |            85 |              85 |             19.9435 |             97.008 |               98.1 |                  0 |         0.0823529 |               0.376471 |                       0 |                   0 |                65 |
|        2000 |         6 | double_touch__high_range_q70__up_a2_b2_wA10_wB10_h6 |             140 |           140 |             140 |             19.0029 |             66.904 |               86.8 |                  0 |         0.378571  |               0.464286 |                       0 |                   0 |                24 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |              68 |            68 |              68 |            19.1206  |             70.854 |               86.8 |                  0 |         0.397059  |               0.529412 |                       0 |                   0 |                14 |
| 2025-02      |              21 |            21 |              21 |            19.8429  |             64.86  |               69.4 |                  0 |         0.47619   |               0.52381  |                       0 |                   0 |                 4 |
| 2025-03      |              26 |            26 |              26 |            15.6731  |             44.425 |               45.3 |                  0 |         0.384615  |               0.423077 |                       0 |                   0 |                 5 |
| 2025-04      |              92 |            92 |              92 |            19.5315  |             98.1   |               98.1 |                  0 |         0.0869565 |               0.369565 |                       0 |                   0 |                72 |
| 2025-05      |              21 |            21 |              21 |            28.9714  |             47.8   |               47.8 |                  0 |         0         |               0.238095 |                       0 |                   0 |                13 |
| 2025-06      |              22 |            22 |              22 |             9.68182 |             23.2   |               23.2 |                  0 |         0.181818  |               0.636364 |                       0 |                   0 |                18 |
| 2025-07      |              28 |            28 |              28 |            26.2286  |             96.8   |               96.8 |                  0 |         0         |               0.357143 |                       0 |                   0 |                24 |
| 2025-08      |               4 |             4 |               4 |            20.025   |             38.611 |               39.1 |                  0 |         0         |               0        |                       0 |                   0 |                 4 |
| 2025-09      |               6 |             6 |               6 |             3.73333 |              8     |                8   |                  0 |         0.333333  |               0.333333 |                       0 |                   0 |                 2 |
| 2025-12      |               8 |             8 |               8 |            24.225   |             55.017 |               56.2 |                  0 |         0.125     |               0.125    |                       0 |                   0 |                 0 |
| 2026-01      |              21 |            21 |              21 |            19.6571  |             38.9   |               39.2 |                  0 |         0.238095  |               0.285714 |                       0 |                   0 |                 4 |
| 2026-02      |               2 |             2 |               2 |             8.7     |             11.542 |               11.6 |                  0 |         0.5       |               0.5      |                       0 |                   0 |                 1 |
| 2026-03      |               7 |             7 |               7 |            18.6143  |             56.878 |               59.2 |                  0 |         0.571429  |               0.714286 |                       0 |                   0 |                 1 |

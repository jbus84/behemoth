# Directional_Inverse Tick-Exact Shortlist Verification

## Setup
- symbol: `USDJPY`
- family_required: `directional_inverse`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/USDJPY_directional_inverse_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDJPY   |               0.9 |             589 |           589 |             589 |            0.790323 |             20.792 |              139.8 |           0.981324 |          0.981324 |                0.98472 |                       0 |                   0 |                 2 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                               |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:---------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        1000 |         6 | directional_inverse__high_activity__h6 |             589 |           589 |             589 |            0.790323 |             20.792 |              139.8 |           0.981324 |          0.981324 |                0.98472 |                       0 |                   0 |                 2 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |              86 |            86 |              86 |            0        |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-02      |              29 |            29 |              29 |            0        |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-03      |              93 |            93 |              93 |            1.7043   |             53.656 |               61.2 |           0.946237 |          0.946237 |               0.956989 |                       0 |                   0 |                 1 |
| 2025-04      |              69 |            69 |              69 |            1.85507  |             40.96  |              128   |           0.985507 |          0.985507 |               0.985507 |                       0 |                   0 |                 0 |
| 2025-05      |              45 |            45 |              45 |            0.155556 |              3.92  |                7   |           0.977778 |          0.977778 |               0.977778 |                       0 |                   0 |                 0 |
| 2025-06      |              56 |            56 |              56 |            0        |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2025-07      |              49 |            49 |              49 |            2.85306  |             72.696 |              139.8 |           0.979592 |          0.979592 |               0.979592 |                       0 |                   0 |                 0 |
| 2025-10      |              21 |            21 |              21 |            0.4      |              4.44  |                4.6 |           0.904762 |          0.904762 |               0.952381 |                       0 |                   0 |                 1 |
| 2025-11      |              25 |            25 |              25 |            0.952    |             18.088 |               23.8 |           0.96     |          0.96     |               0.96     |                       0 |                   0 |                 0 |
| 2025-12      |              25 |            25 |              25 |            0        |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-01      |              37 |            37 |              37 |            0        |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-02      |              17 |            17 |              17 |            0        |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
| 2026-03      |              37 |            37 |              37 |            0        |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |

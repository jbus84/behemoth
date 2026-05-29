# Directional_Run Tick-Exact Shortlist Verification

## Setup
- symbol: `EURUSD`
- family_required: `directional_run`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_directional_run_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| EURUSD   |               0.9 |            1473 |          1473 |            1473 |             8.71568 |             40.504 |              110.2 |         0.00814664 |        0.00814664 |             0.00814664 |                       0 |                   0 |                 0 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                                      |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|         100 |         6 | directional_run__high_range_q70__n3_reversion |            1473 |          1473 |            1473 |             8.71568 |             40.504 |              110.2 |         0.00814664 |        0.00814664 |             0.00814664 |                       0 |                   0 |                 0 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-01      |             186 |           186 |             186 |             8.32258 |             30.68  |               66.4 |         0          |        0          |             0          |                       0 |                   0 |                 0 |
| 2025-02      |              98 |            98 |              98 |             9.00612 |             35.936 |               46.8 |         0          |        0          |             0          |                       0 |                   0 |                 0 |
| 2025-03      |              97 |            97 |              97 |             7.64124 |             32.168 |               36.2 |         0          |        0          |             0          |                       0 |                   0 |                 0 |
| 2025-04      |             402 |           402 |             402 |            11.3711  |             62.884 |              110.2 |         0.00746269 |        0.00746269 |             0.00746269 |                       0 |                   0 |                 0 |
| 2025-08      |              91 |            91 |              91 |             8.24396 |             27.02  |               75.8 |         0          |        0          |             0          |                       0 |                   0 |                 0 |
| 2025-09      |              90 |            90 |              90 |             6.64222 |             20.234 |               28.6 |         0.0111111  |        0.0111111  |             0.0111111  |                       0 |                   0 |                 0 |
| 2025-10      |              98 |            98 |              98 |             6.51633 |             22.15  |               27   |         0.0204082  |        0.0204082  |             0.0204082  |                       0 |                   0 |                 0 |
| 2025-11      |              76 |            76 |              76 |             6.11316 |             19.65  |               22.8 |         0.0394737  |        0.0394737  |             0.0394737  |                       0 |                   0 |                 0 |
| 2025-12      |              39 |            39 |              39 |             5.67179 |             18     |               18   |         0          |        0          |             0          |                       0 |                   0 |                 0 |
| 2026-01      |             115 |           115 |             115 |             9.08522 |             48.264 |               78.8 |         0.0173913  |        0.0173913  |             0.0173913  |                       0 |                   0 |                 0 |
| 2026-02      |              51 |            51 |              51 |             7.23922 |             29.8   |               31.4 |         0          |        0          |             0          |                       0 |                   0 |                 0 |
| 2026-03      |             130 |           130 |             130 |             7.76    |             32.118 |               50.4 |         0.00769231 |        0.00769231 |             0.00769231 |                       0 |                   0 |                 0 |

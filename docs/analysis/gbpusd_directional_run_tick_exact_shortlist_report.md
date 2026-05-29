# Directional_Run Tick-Exact Shortlist Verification

## Setup
- symbol: `GBPUSD`
- family_required: `directional_run`
- locked_quantile: `0.9`
- selection_mode: `auto`
- abs_tol_pips: `1e-09`
- shortlist_state_csv: `data/analysis/tick_opportunity_mining/reduced_core_rolling/GBPUSD_directional_run_reduced_state_schedule.csv`

## Summary
| symbol   |   locked_quantile |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| GBPUSD   |               0.9 |             454 |           454 |             454 |             34.3361 |            118.588 |              201.6 |                  0 |                 0 |                      0 |                       0 |                   0 |                 0 |                  0.999 |                      0.999 | False              | False                  | True         | False          |

## By State
|   bar_ticks |   horizon | state_id                                      |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:----------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|        2000 |         6 | directional_run__high_intensity__n2_reversion |             454 |           454 |             454 |             34.3361 |            118.588 |              201.6 |                  0 |                 0 |                      0 |                       0 |                   0 |                 0 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-03      |              81 |            81 |              81 |             28.5259 |             96.32  |               97.6 |                  0 |                 0 |                      0 |                       0 |                   0 |                 0 |
| 2025-04      |              87 |            87 |              87 |             36.1011 |            120.244 |              201.6 |                  0 |                 0 |                      0 |                       0 |                   0 |                 0 |
| 2025-05      |              36 |            36 |              36 |             45.1    |            155.32  |              175.2 |                  0 |                 0 |                      0 |                       0 |                   0 |                 0 |
| 2025-06      |              28 |            28 |              28 |             27.7429 |             92.374 |               98.8 |                  0 |                 0 |                      0 |                       0 |                   0 |                 0 |
| 2025-07      |              46 |            46 |              46 |             43.5087 |            127.4   |              132.8 |                  0 |                 0 |                      0 |                       0 |                   0 |                 0 |
| 2025-12      |              53 |            53 |              53 |             25.234  |             76.616 |               81.4 |                  0 |                 0 |                      0 |                       0 |                   0 |                 0 |
| 2026-01      |              67 |            67 |              67 |             32.3403 |             90.764 |              100.4 |                  0 |                 0 |                      0 |                       0 |                   0 |                 0 |
| 2026-02      |              15 |            15 |              15 |             34.6267 |             90.9   |               91.6 |                  0 |                 0 |                      0 |                       0 |                   0 |                 0 |
| 2026-03      |              41 |            41 |              41 |             41.7512 |            111.16  |              115.8 |                  0 |                 0 |                      0 |                       0 |                   0 |                 0 |

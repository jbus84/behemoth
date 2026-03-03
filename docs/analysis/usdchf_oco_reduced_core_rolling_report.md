# OCO Tick-Exact Shortlist Verification

## Setup
- symbol: `USDCHF`
- family_required: `oco_first_touch_clean`
- locked_quantile: `0.9`
- selection_mode: `auto`
- oco_hold_mode: `from_touch`
- oco_include_no_touch: `True`
- abs_tol_pips: `1e-09`

## Summary
| symbol   |   locked_quantile | oco_hold_mode   | oco_include_no_touch   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|:----------------|:-----------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| USDCHF   |               0.9 | from_touch      | True                   |           30450 |         30450 |           30450 |           0.0899343 |                3.3 |               48.8 |           0.985517 |          0.985452 |               0.997209 |                     443 |                 443 |               101 |                  0.999 |                      0.999 | False              | False                  | False        | False          |

## By State
|   bar_ticks |   horizon | state_id                                    |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:--------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|         100 |         5 | oco_first_touch_clean__ny_overlap__k2       |             888 |           888 |             888 |             1.12027 |             15.626 |               48.2 |           0.815315 |          0.815315 |               0.96509  |                     164 |                 164 |                47 |
|         100 |         6 | oco_first_touch_clean__high_abs_vel_q80__k2 |            6454 |          6454 |            6454 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_range_q70__k2   |            7551 |          7551 |            7551 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_range_q80__k2   |            8475 |          8475 |            8475 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__london__k2           |            5758 |          5758 |            5758 |             0       |              0     |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__ny_overlap__k2       |            1324 |          1324 |            1324 |             1.31699 |             18.116 |               48.8 |           0.790785 |          0.789275 |               0.959215 |                     279 |                 279 |                54 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-04      |           12747 |         12747 |           12747 |           0.150608  |              5.3   |               48.8 |           0.978034 |          0.977877 |               0.995215 |                     282 |                 282 |                21 |
| 2025-05      |            4462 |          4462 |            4462 |           0.0443299 |              0     |               19.7 |           0.992156 |          0.992156 |               0.998879 |                      35 |                  35 |                 1 |
| 2025-06      |            3041 |          3041 |            3041 |           0.0165735 |              0     |                8.9 |           0.995067 |          0.995067 |               0.998685 |                      15 |                  15 |                 0 |
| 2025-07      |            1753 |          1753 |            1753 |           0.0428979 |              0.288 |                8   |           0.989732 |          0.989732 |               0.998289 |                      18 |                  18 |                24 |
| 2025-08      |            2337 |          2337 |            2337 |           0.0071887 |              0     |                4.3 |           0.997861 |          0.997861 |               0.999572 |                       5 |                   5 |                 6 |
| 2025-09      |            1667 |          1667 |            1667 |           0.10018   |              4.2   |               16.8 |           0.982603 |          0.982603 |               0.995801 |                      29 |                  29 |                 6 |
| 2025-10      |            1559 |          1559 |            1559 |           0.118409  |              4.71  |               21   |           0.980757 |          0.980757 |               0.998717 |                      30 |                  30 |                 8 |
| 2025-11      |            1734 |          1734 |            1734 |           0.0638985 |              3.567 |                7.8 |           0.985006 |          0.985006 |               0.998847 |                      26 |                  26 |                31 |
| 2025-12      |            1150 |          1150 |            1150 |           0.014     |              0     |                6   |           0.997391 |          0.997391 |               1        |                       3 |                   3 |                 4 |

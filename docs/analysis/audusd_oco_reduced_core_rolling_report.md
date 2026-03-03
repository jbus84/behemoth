# OCO Tick-Exact Shortlist Verification

## Setup
- symbol: `AUDUSD`
- family_required: `oco_first_touch_clean`
- locked_quantile: `0.9`
- selection_mode: `auto`
- oco_hold_mode: `from_touch`
- oco_include_no_touch: `True`
- abs_tol_pips: `1e-09`

## Summary
| symbol   |   locked_quantile | oco_hold_mode   | oco_include_no_touch   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |   min_exact_match_rate |   min_pos_label_match_rate | pass_exact_match   | pass_pos_label_match   | pass_clean   | overall_pass   |
|:---------|------------------:|:----------------|:-----------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|-----------------------:|---------------------------:|:-------------------|:-----------------------|:-------------|:---------------|
| AUDUSD   |               0.9 | from_touch      | True                   |           29804 |         29804 |           29804 |            0.136515 |                5.1 |               46.3 |           0.976043 |          0.975909 |               0.995403 |                     718 |                 718 |               262 |                  0.999 |                      0.999 | False              | False                  | False        | False          |

## By State
|   bar_ticks |   horizon | state_id                                    |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|------------:|----------:|:--------------------------------------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
|         100 |         5 | oco_first_touch_clean__ny_overlap__k2       |            1514 |          1514 |            1514 |             1.12992 |               14.3 |               46.3 |           0.797886 |          0.797886 |               0.964993 |                     306 |                 306 |               126 |
|         100 |         6 | oco_first_touch_clean__high_abs_vel_q80__k2 |            6598 |          6598 |            6598 |             0       |                0   |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_range_q70__k2   |            7237 |          7237 |            7237 |             0       |                0   |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__high_range_q80__k2   |            8130 |          8130 |            8130 |             0       |                0   |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__london__k2           |            4495 |          4495 |            4495 |             0       |                0   |                0   |           1        |          1        |               1        |                       0 |                   0 |                 0 |
|         100 |         6 | oco_first_touch_clean__ny_overlap__k2       |            1830 |          1830 |            1830 |             1.28852 |               14.7 |               43.4 |           0.777049 |          0.774863 |               0.954098 |                     412 |                 412 |               136 |

## By Month
| test_month   |   rows_selected |   rows_mapped |   rows_verified |   mean_abs_err_pips |   p99_abs_err_pips |   max_abs_err_pips |   exact_match_rate |   sign_match_rate |   pos_label_match_rate |   clean_violation_count |   both_window_count |   undecided_count |
|:-------------|----------------:|--------------:|----------------:|--------------------:|-------------------:|-------------------:|-------------------:|------------------:|-----------------------:|------------------------:|--------------------:|------------------:|
| 2025-04      |           13646 |         13646 |           13646 |          0.257914   |              7.855 |               46.3 |           0.955958 |          0.955665 |               0.992012 |                     605 |                 605 |               239 |
| 2025-05      |            3740 |          3740 |            3740 |          0.0125936  |              0     |               10.8 |           0.996257 |          0.996257 |               0.999198 |                      14 |                  14 |                 4 |
| 2025-06      |            3112 |          3112 |            3112 |          0.0294023  |              0     |                9   |           0.992931 |          0.992931 |               0.998072 |                      22 |                  22 |                 1 |
| 2025-07      |            2431 |          2431 |            2431 |          0.0331551  |              0     |                9.3 |           0.993007 |          0.993007 |               0.998355 |                      17 |                  17 |                 4 |
| 2025-08      |            1488 |          1488 |            1488 |          0.00907258 |              0     |                4.2 |           0.997312 |          0.997312 |               1        |                       4 |                   4 |                 2 |
| 2025-09      |            1496 |          1496 |            1496 |          0.0901738  |              4     |               12   |           0.980615 |          0.980615 |               0.993984 |                      29 |                  29 |                 2 |
| 2025-10      |            1423 |          1423 |            1423 |          0.0848911  |              0     |               29.8 |           0.990162 |          0.990162 |               0.996486 |                      14 |                  14 |                 0 |
| 2025-11      |            1398 |          1398 |            1398 |          0.0171674  |              0     |                9.3 |           0.995708 |          0.995708 |               0.999285 |                       6 |                   6 |                 8 |
| 2025-12      |            1070 |          1070 |            1070 |          0.0343925  |              0     |               11   |           0.993458 |          0.993458 |               1        |                       7 |                   7 |                 2 |
